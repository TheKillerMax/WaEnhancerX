#!/usr/bin/env python3
"""Compile the screen inventory effects and the complete reader on the host JVM.

Run from repo root. --ref reads production sources (not the test) from Git.
--mutants additionally compiles temporary defects and requires specific behavioral
failures. The fixture models one keyed effect, not the Compose scheduler.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path('app/src/main/java/com/waenhancer')
SCREENS = {
    'Dashboard': ('ui/screens/dashboard/MainDashboardScreen.kt', 'systemDiagnostics', 'diagnosticsRefreshTrigger'),
    'Health': ('ui/screens/settings/SystemHealthScreen.kt', 'diagnostics', 'refreshTrigger'),
}
FIXTURE = ROOT / 'qa/fixtures/DiagnosticsRefreshChecks.kt'

# Only external boundaries used by SystemDiagnostics.kt or the callbacks. No su,
# shell executable, Android framework, or replacement implementation of the cache.
STUBS = {
    'Context.kt': '''package android.content
class Context {
    val packageName = "fixture.manager"
    val packageManager = android.content.pm.PackageManager(packageName)
}
''',
    'PM.kt': '''package android.content.pm
class ApplicationInfo
class PackageInfo {
    val versionName = "fixture"
    val versionCode = 1
    val longVersionCode = 1L
    val applicationInfo: ApplicationInfo? = ApplicationInfo()
}
class PackageManager(val own: String) {
    fun getPackageInfo(name: String, flags: Int): PackageInfo {
        require(name == own)
        return PackageInfo()
    }
    fun getApplicationLabel(info: ApplicationInfo): CharSequence = "fixture"
}
''',
    'Build.kt': '''package android.os
object Build {
    val MANUFACTURER = "fixture"
    val MODEL = "host"
    val SUPPORTED_ABIS = arrayOf("fixture")
    object VERSION { const val SDK_INT = 30; const val RELEASE = "11" }
}
object SELinux {
    var enforced = false
    @JvmStatic fun isSELinuxEnforced() = enforced
}
''',
    'Config.kt': '''package com.waenhancer.app
object BuildConfig {
    const val VERSION_NAME = "fixture"
    const val VERSION_CODE = 1
    const val GIT_SHA = "fixture"
    const val MAPPING_ID = "fixture"
}
''',
    'Prefs.kt': '''package com.waenhancer.config
object PreferenceStores { fun publicStore(context: android.content.Context) = Store() }
class Store {
    fun getInt(key: String, fallback: Int) = fallback
    fun getString(key: String, fallback: String?) = fallback
    fun getStringSet(key: String, fallback: Set<String>?): Set<String>? = fallback
}
''',
    'Targets.kt': '''package com.waenhancer.utils
object TargetAppManager {
    fun isModuleActive() = false
    fun refresh(context: android.content.Context) = Unit
}
''',
    'RootAccess.kt': '''package com.waenhancer.update
object UpdateDownloader {
    val requests = mutableListOf<Boolean>()
    fun hasCachedRootAccess(): Boolean? = true
    fun hasRootAccess(force: Boolean): Boolean { requests.add(force); return true }
}
''',
    'Command.kt': '''package com.waenhancer.xposed.utils
object AppRestartHelper {
    fun runRootCommand(command: String): String {
        require(command == "getenforce")
        return if (android.os.SELinux.enforced) "Enforcing" else "Permissive"
    }
}
''',
}


def one(pattern, text):
    matches = re.findall(pattern, text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f'Expected one match for {pattern!r}, found {len(matches)}; review screen projection')
    return matches[0]


def projection(name, source, screen):
    """Project actual state declarations, callbacks and the one inventory effect.

    Deliberately scoped to these screens, not a general Kotlin parser. Only the
    counter updates in the confirmed settings reset are relevant to inventory.
    """
    _, state, counter = SCREENS[screen]
    ints = '\n'.join(re.findall(r'^    var \w+ by remember \{ mutableIntStateOf\([^()\n]*\) \}$', source, re.M))
    snapshot = one(r'^    var ' + state + r' by remember \{\n.*?^    \}', source)
    effects = re.findall(r'^    LaunchedEffect\([^\n]*\) \{\n.*?^    \}', source, re.M | re.S)
    effect, = [block for block in effects if 'SystemDiagnosticsReader.read(' in block]
    if source.count('SystemDiagnosticsReader.read(') != 1 or 'SystemDiagnosticsReader.getOrFastSnapshot(' not in snapshot:
        raise ValueError(f'{screen}: inventory no longer confined to expected paths')
    observer = one(r'val observer = LifecycleEventObserver \{ _, event ->\n(.*?)^        \}', source)
    alias = reset = ''
    if screen == 'Dashboard':
        alias = 'val isModuleActive get() = ' + one(r'^    val isModuleActive = ([^\n]+)$', source)
        click = one(r'^                onRefresh = \{\n(.*?)^                \},', source)
        one(r'IconButton\(\s*onClick = onRefresh,', source)
        sheet = one(r'if \(showResetSettingsDialog\) \{(.*?)^        \}', source)
        confirm = one(r'onConfirm = \{(.*?)^                \}', sheet)
        reset = '\n'.join(re.findall(r'^                    (\w+\+\+)$', confirm, re.M))
    else:
        click = one(r'IconButton\(onClick = \{([^{}\n]*)\}\) \{\s*Icon\(\s*imageVector = WaexIcons\.Refresh,\s*contentDescription = UiText\.get\(R\.string\.waex_ui_refresh_diagnostics,', source)
    increment = counter + '++'
    if source.count(increment) != sum(s.count(increment) for s in (click, observer, reset)):
        raise ValueError(f'{screen}: unaccounted refresh producer')
    return f'''class {name} : Screen() {{
    {alias}
{ints}
{snapshot}
    override val shown get() = {state}
    override fun click() {{ {click} }}
    override fun lifecycle(event: Lifecycle.Event) {{ {observer} }}
    override fun reset() {{ {reset} }}
    override fun render() {{
{effect}
    }}
}}
'''


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one mutation site: {old}')
    return text.replace(old, new)


def mutants(source, screen):
    _, state, counter = SCREENS[screen]
    yield 'Sticky', 'module', replace_one(source, 'generation != completedDiagnosticsRefresh', 'generation > 0')
    ack = '        completedDiagnosticsRefresh = generation\n'
    read = f'        {state} = withContext(Dispatchers.IO)'
    early = replace_one(source, ack, '')
    yield 'EarlyAck', 'restart', replace_one(early, read, ack + read)
    yield 'LiveAck', 'queued', replace_one(source, ack, f'        completedDiagnosticsRefresh = {counter}\n')
    active = 'isModuleActive' if screen == 'Dashboard' else 'moduleActivation.active'
    keys = f'LaunchedEffect({counter}, {active})'
    yield 'TargetKey', 'target', replace_one(source, keys, keys[:-1] + ', scopeSnapshot)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', help='use reader and screens from this local Git revision')
    parser.add_argument('--mutants', action='store_true', help='also check causal mutants of the candidate')
    args = parser.parse_args()

    def production(relative):
        path = PACKAGE / relative
        if args.ref:
            return subprocess.check_output(['git', 'show', f'{args.ref}:{path.as_posix()}'], cwd=ROOT)
        return (ROOT / path).read_bytes()

    with tempfile.TemporaryDirectory(prefix='waex-refresh-') as temp:
        out = Path(temp)
        for filename, body in STUBS.items():
            (out / filename).write_text(body, encoding='utf-8')
        (out / 'SystemDiagnostics.kt').write_bytes(production('utils/SystemDiagnostics.kt'))
        classes, branches, cases = [], [], []
        for screen, (path, _, _) in SCREENS.items():
            source = production(path).decode('utf-8')
            variants = [('', None, source)]
            if args.mutants:
                variants.extend(mutants(source, screen))
            for suffix, expected_failure, text in variants:
                name = screen + suffix
                classes.append(projection(name, text, screen))
                has_reset = 'true' if screen == 'Dashboard' else 'false'
                branches.append(f'    "{name}" -> verify({has_reset}) {{ {name}() }}')
                cases.append((name, expected_failure))
        driver = 'fun main(args: Array<String>) { when (args.single()) {\n' + '\n'.join(branches) + '\n    else -> error("unknown screen")\n} }\n'
        (out / 'Screens.kt').write_text('package com.waenhancer.utils\n' + '\n'.join(classes) + driver, encoding='utf-8')
        jar = out / 'refresh.jar'
        subprocess.run(['kotlinc', '-nowarn', '-language-version', '2.0', '-jvm-target', '17', str(FIXTURE),
                        *map(str, sorted(out.glob('*.kt'))), '-include-runtime', '-d', str(jar)], check=True, timeout=120)
        ok = True
        for name, expected_failure in cases:
            # Fresh process per screen/mutant: don't clear production singleton fields by reflection.
            run = subprocess.run(['java', '-cp', str(jar), 'com.waenhancer.utils.ScreensKt', name],
                                 capture_output=True, text=True, timeout=30)
            failure = re.search(r'REFRESH_ASSERT\|([^|\n]+)\|[^\n]*', run.stderr)
            if expected_failure is None and run.returncode == 0:
                print(f'PASS {name}: diagnostics refresh sequence', flush=True)
            elif expected_failure and run.returncode != 0 and failure and failure[1] == expected_failure:
                print(f'KILLED {name}: {failure[0]}', flush=True)
            else:
                print(f'FAIL {name}: {failure[0] if failure else run.stdout + run.stderr or "unexpected success"}', flush=True)
                ok = False
        return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
