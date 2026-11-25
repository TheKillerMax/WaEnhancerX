#!/usr/bin/env python3
"""Exercise current floating-bar method bodies and the complete overlay launcher.

Uses real Robolectric 4.17, Android API 24/28/34, Core 1.18.0 and DexKit 2.2.0.
The exported product tree lacks ScreenScopedFeature. This runner makes and records
THREE declaration-only edits in a temporary copy: its import, implements clause
and the override annotation on onScreenDisposed. Every method body is retained.
It does not replace the missing contract with a fake interface and does not prove
complete-hook compilation, FeatureRegistry dispatch, APK/Compose compilation,
LSPosed injection, host selectors, OEM settings UI or GPU rendering.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tomllib
import zipfile

import android_media_preview_test as framework
from kotlin_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('app/src/main/java/com/waenhancer')
HOOK = JAVA/'xposed/features/customization/FloatingBottomBarHook.java'
BASE = JAVA/'xposed/core/BaseFeature.kt'
OVERLAY = JAVA/'app/OverlayPermissionLauncher.java'
SUPPORT = [JAVA/p for p in (
    'xposed/core/HookRegistrar.java', 'xposed/core/ViewHookDispatcher.java',
    'xposed/utils/HostResourceIds.java', 'xposed/utils/HookErrors.java',
    'xposed/core/privacy/PrivacyPrefs.java', 'xposed/core/privacy/PrivacyToggle.java',
    'xposed/core/wa/WaJid.java', 'config/DndPreferencePolicy.java')]
FIXTURES = ROOT/'qa/fixtures/floating_bottom_bar'
CORE_URL = 'https://dl.google.com/dl/android/maven2/androidx/core/core/1.18.0/core-1.18.0.aar'
CORE_AAR_SHA256 = '311d83ac67d394076ec21d12ed2d10a44b59cb2929b7dce00e5a90a93842e37d'
CORE_SHA256 = 'd1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0'
ANNOTATION_URL = 'https://dl.google.com/dl/android/maven2/androidx/annotation/annotation-jvm/1.9.1/annotation-jvm-1.9.1.jar'
ANNOTATION_SHA256 = '1e343917ebf27ba96fe4dc52b1cad7fd32b738fbc6355bb6cd5b3b305d7212d0'
LEGACY_FAILURES = {
    'unchangedSelectionDoesNotScheduleAnotherRedraw',
    'repeatedSelectionDoesNotRetainTransitionHistory',
    'unchangedNativeIndicatorDoesNotReplaceItsBackground',
    'zeroHeightContainerDoesNotPollTheMainLooper',
    'firstNonzeroLayoutPositionsFabWithoutWaitingForATimer',
    'detachedEmptyContainerSchedulesNoFurtherWork',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_hook(original):
    """Remove unavailable type declarations only; invert and check every edit."""
    edits = [
        ('import com.waenhancer.hooking.ScreenScopedFeature;\n', ''),
        ('extends BaseFeature implements ScreenScopedFeature {', 'extends BaseFeature {'),
        ('    @Override\n    public void onScreenDisposed(@NonNull Activity activity) {',
         '    public void onScreenDisposed(@NonNull Activity activity) {'),
    ]
    projected = original
    records = []
    for before, after in edits:
        if projected.count(before) != 1:
            raise RuntimeError('Unavailable-contract projection no longer matches exactly')
        index = projected.index(before)
        projected = projected[:index] + after + projected[index+len(before):]
        records.append({'offset': index, 'before': before, 'after': after})
    restored = projected
    for change in reversed(records):
        index = change['offset']
        if restored[index:index+len(change['after'])] != change['after']:
            raise RuntimeError('Projection inverse mismatch')
        restored = restored[:index] + change['before'] + restored[index+len(change['after']):]
    if restored != original:
        raise RuntimeError('Projection modified a method body')
    return projected, records


def pinned_jar(provided, url, archive_sha, jar_sha, out, name, limit):
    if provided:
        return framework.verify_api(provided.resolve(), jar_sha, limit)
    target = out/'public-apis'/name
    if archive_sha:
        archive = framework.download_pinned(url, target.with_suffix('.aar'), archive_sha, 8*1024*1024)
        with zipfile.ZipFile(archive) as bundle:
            matches = [entry for entry in bundle.infolist() if entry.filename == 'classes.jar']
            if len(matches) != 1 or matches[0].file_size > limit:
                raise RuntimeError('API AAR lacks one bounded classes.jar')
            target.write_bytes(bundle.read(matches[0]))
    else:
        framework.download_pinned(url, target, jar_sha, limit)
    return framework.verify_api(target, jar_sha, limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--dexkit-jar', type=Path)
    parser.add_argument('--core-api-jar', type=Path)
    parser.add_argument('--annotation-api-jar', type=Path)
    parser.add_argument('--sdk-jars', type=Path)
    parser.add_argument('--maven', default='mvn')
    parser.add_argument('--maven-repo', type=Path)
    parser.add_argument('--maven-settings', type=Path)
    parser.add_argument('--legacy-baseline', action='store_true',
                        help='Run the ten original floating tests on current pre-port source; require six exact failures per SDK')
    parser.add_argument('--expected-failures', type=Path,
                        help='Exact method-name/count map for a causal mutation; all failures must be assertion errors')
    args = parser.parse_args()
    if args.legacy_baseline and args.expected_failures:
        parser.error('Select a baseline or a mutation, not both')
    root, out = args.source_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if tomllib.loads((root/'gradle/libs.versions.toml').read_text(encoding='utf-8'))['versions']['androidxCore'] != '1.18.0':
        raise RuntimeError('Update Core artifact for the changed project catalog')
    dependencies_dir = framework.resolve_framework(args, out)
    core = pinned_jar(args.core_api_jar, CORE_URL, CORE_AAR_SHA256, CORE_SHA256,
                      out, 'core-1.18.0.jar', 4*1024*1024)
    annotation = pinned_jar(args.annotation_api_jar, ANNOTATION_URL, None, ANNOTATION_SHA256,
                            out, 'annotation-jvm-1.9.1.jar', 1024*1024)
    dexkit = pinned_jar(args.dexkit_jar, framework.DEXKIT_URL, framework.DEXKIT_AAR_SHA256,
                        framework.DEXKIT_SHA256, out, 'dexkit-2.2.0.jar', 2*1024*1024)
    kotlin_home, compiler = framework.find_kotlin()
    framework.run([*compiler_command(compiler), '-version'], out/'kotlin-version.log', timeout=45)
    if 'kotlinc-jvm 2.0.20 ' not in (out/'kotlin-version.log').read_text(encoding='utf-8'):
        raise RuntimeError('The compiler must be exactly Kotlin 2.0.20')
    compiler_files = [compiler, kotlin_home/'lib/kotlin-compiler.jar']
    preloader = kotlin_home/'lib/kotlin-preloader.jar'
    if preloader.is_file():
        compiler_files.append(preloader)
    (out/'toolchain-sha256.json').write_text(json.dumps({str(p): digest(p) for p in
        compiler_files}, indent=2)+'\n')
    dependencies = sorted(dependencies_dir.glob('*.jar')) + [core, annotation, dexkit, kotlin_home/'lib/kotlin-stdlib.jar']
    (out/'dependency-sha256.json').write_text(json.dumps({str(p): digest(p) for p in dependencies}, indent=2)+'\n')
    if args.sdk_jars:
        (out/'sdk-sha256.json').write_text(json.dumps({p.name: digest(p) for p in sorted(args.sdk_jars.glob('*.jar'))}, indent=2)+'\n')
    stage, classes = out/'sources', out/'classes'
    classes.mkdir()
    paths = [HOOK, BASE] + SUPPORT + ([] if args.legacy_baseline else [OVERLAY])
    identities = {str(p): digest(root/p) for p in [Path('gradle/libs.versions.toml')]}
    identities.update({str(p): digest(ROOT/p) for p in [Path('qa/kotlin_compiler.py'),
        Path('qa/android_media_preview_test.py'), Path('qa/maven_dependencies.py')]})
    sources = []
    for relative in paths:
        source, destination = root/relative, stage/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        identities[str(relative)] = digest(source)
        sources.append(destination)
    original = (stage/HOOK).read_bytes().decode('utf-8')
    projected, edits = project_hook(original)
    (stage/HOOK).write_text(projected, encoding='utf-8')
    (out/'source-projection.json').write_text(json.dumps({
        'original_sha256': identities[str(HOOK)], 'projected_sha256': digest(stage/HOOK),
        'edits': edits, 'inverse_restores_all_source': True,
        'complete_hook_compilation': False,
        'missing_contract': 'com.waenhancer.hooking.ScreenScopedFeature',
        'product_files_modified_by_projection': False,
    }, indent=2)+'\n')
    fixture = FIXTURES/'runtime_doubles.py'
    identities[str(fixture.relative_to(ROOT))] = digest(fixture)
    doubles = runpy.run_path(str(fixture))['STUBS']
    if any(name.startswith(('android/', 'androidx/', 'org/luckypray/')) for name in doubles):
        raise RuntimeError('Android/Core/DexKit APIs must not be replaced by fixture classes')
    ids = sorted(set(re.findall(r'R\.string\.(\w+)', '\n'.join((root/p).read_text(encoding='utf-8') for p in paths))))
    doubles['com/waenhancer/app/R.java'] = ('package com.waenhancer.app; public final class R { public static final class string {'
        + ''.join(f'public static final int {key}={i+1};' for i,key in enumerate(ids)) + '}}')
    double_identities = {}
    for name, text in doubles.items():
        destination = stage/'host-boundaries'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding='utf-8')
        sources.append(destination)
        double_identities[name] = digest(destination)
    tests = ['FloatingBottomBarLifecycleTest.java']
    if not args.legacy_baseline:
        tests += ['OverlayPermissionLauncherTest.java', 'FloatingBottomBarOwnershipTest.java']
    cases = {'FloatingBottomBarLifecycleTest.java': 10, 'OverlayPermissionLauncherTest.java': 7,
             'FloatingBottomBarOwnershipTest.java': 10}
    expected_cases = 0
    for name in tests:
        source, destination = FIXTURES/name, stage/name
        shutil.copyfile(source, destination)
        identities['qa/fixtures/floating_bottom_bar/'+name] = digest(source)
        if len(re.findall(r'@Test\b', source.read_text(encoding='utf-8'))) != cases[name]:
            raise RuntimeError('Regression fixture case inventory changed: ' + name)
        expected_cases += cases[name] * 3
    # Kotlin sees only actual production dependencies and Java source symbols, not
    # the newer metadata shipped by the test runtime. No skip-metadata flag is used.
    android = dependencies_dir/'android-all-14-robolectric-10818077.jar'
    production_cp = os.pathsep.join(map(str, [android, annotation, core, dexkit, kotlin_home/'lib/kotlin-stdlib.jar']))
    cp = str(classes) + os.pathsep + os.pathsep.join(map(str, dependencies))
    framework.run([*compiler_command(compiler), '-jvm-target', '17', '-classpath', production_cp,
                   '-d', str(classes), *map(str,sources)], out/'kotlinc-current-base.log', timeout=240)
    framework.run(['javac','--release','17','-encoding','UTF-8','-cp',cp,'-d',str(classes),
                   *[str(p) for p in sources if p.suffix == '.java']], out/'javac-product-methods.log', timeout=240)
    framework.run(['javac','--release','17','-encoding','UTF-8','-cp',cp,'-d',str(classes),
                   *[str(stage/name) for name in tests]], out/'javac-tests.log', timeout=180)
    opens = ['java.base/java.lang','java.base/java.util','java.base/java.util.concurrent',
             'java.base/java.io','java.base/java.net','java.base/java.security','java.base/java.text',
             'java.base/jdk.internal.access','java.desktop/java.awt.font','jdk.compiler/com.sun.tools.javac.api']
    command = ['java','-Xmx1g',*['--add-opens='+p+'=ALL-UNNAMED' for p in opens],
               '-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2']
    if args.sdk_jars:
        command += ['-Drobolectric.offline=true','-Drobolectric.dependency.dir='+str(args.sdk_jars.resolve())]
    if args.maven_repo:
        command += ['-Dmaven.repo.local='+str(args.maven_repo.resolve())]
    command += ['-cp',cp,'org.junit.runner.JUnitCore']
    command += [('com.waenhancer.app.' if name.startswith('Overlay') else
                 'com.waenhancer.xposed.features.customization.')+Path(name).stem for name in tests]
    result = framework.run(command,out/'junit.log',allow_failure=True,timeout=240)
    junit = (out/'junit.log').read_text(encoding='utf-8')
    expected = {name:3 for name in LEGACY_FAILURES} if args.legacy_baseline else (
        json.loads(args.expected_failures.read_text(encoding='utf-8')) if args.expected_failures else {})
    passed = re.search(r'OK \((\d+) tests?\)',junit)
    failed = re.search(r'Tests run: (\d+),\s+Failures: (\d+)',junit)
    executed = int(passed[1]) if passed else int(failed[1]) if failed else 0
    entries = re.findall(r'^\d+\) ([^(\[]+)(?:\[[^\n]*?\])?\([^\n]+\)\n([^\n]+)',junit,re.M)
    observed = {}
    for name,error in entries:
        observed[name] = observed.get(name,0)+1
    failure_count = int(failed[2]) if failed else 0
    assertion_only = all(error.startswith(('java.lang.AssertionError','org.junit.ComparisonFailure')) for _,error in entries)
    valid = executed == expected_cases and observed == expected and assertion_only
    valid = valid and failure_count == sum(expected.values()) and len(entries) == failure_count
    valid = valid and ((result == 0 and passed is not None) if not expected else (result != 0 and failed is not None))
    identities['qa/android_floating_bottom_bar_methods_test.py'] = digest(Path(__file__))
    record = {'source_root':str(root),'junit_exit_code':result,'tests':executed,'expected_tests':expected_cases,
        'assertion_failures':failure_count,'observed_failure_methods':observed,'expected_failure_methods':expected,
        'accepted_result':valid,'complete_hook_compilation':False,'all_product_method_bodies_retained':True,
        'source_sha256':identities,'host_boundary_sha256':double_identities,'limits':__doc__}
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    if not valid:
        print(junit[-16000:])
        raise RuntimeError('Unexpected bounded method/overlay result')
    print(json.dumps({k:record[k] for k in ['tests','assertion_failures','accepted_result','complete_hook_compilation']}))


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print('ERROR:',error,flush=True)
        raise SystemExit(2)
