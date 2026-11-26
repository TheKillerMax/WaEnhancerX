#!/usr/bin/env python3
"""Complete recorder and schema with real Android preferences, Bundle and file descriptors.

Robolectric 4.17, Android 24/28/34, JUnit 4.13.2 and DexKit 2.2.0 API.
MediaRecorder's native boundary uses an explicit shadow: it does not capture sound,
write encoded audio or validate device routing. Host, Xposed, scheduler, storage
authorization and native DexKit discovery are fixtures. No APK or root execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from prepare_dexkit import DEFAULT_CACHE, acquire
from test_call_recording_lifecycle import STUBS

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('app/src/main/java/com/waenhancer')
JAVA_FIRST = [BASE / name for name in ('config/PreferenceSchema.java', 'config/PreferenceStores.java',
    'config/ExclusivePreferences.java', 'calls/RecordingOutputFiles.java', 'xposed/utils/HookErrors.java')]
JAVA_LIFECYCLE = [BASE / name for name in ('xposed/core/HookRegistrar.java', 'xposed/core/ViewHookDispatcher.java')]
KOTLIN = [BASE / name for name in ('xposed/core/BaseFeature.kt', 'core/preferences/SettingsBackupCodec.kt')]
JAVA_HOOK = [BASE / name for name in (
    'xposed/bridge/client/HookProviderIpc.java',
    'core/preferences/WaexPreferenceManager.java',
    'xposed/features/media/CallRecordingHook.java',
    'xposed/features/media/CallRecordingEventContract.java')]
PRODUCTION = JAVA_FIRST + KOTLIN + JAVA_LIFECYCLE + JAVA_HOOK
FIXTURE = Path('qa/fixtures/CallRecordingAudioAndroidTest.java')
EXPECTED_TESTS = 81

DEXKIT_SHA256 = '195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1'
POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>org.waex.qa</groupId>
<artifactId>call-recording-audio-qa-only</artifactId><version>1</version>
<repositories><repository><id>google</id><url>https://dl.google.com/dl/android/maven2/</url></repository></repositories>
<dependencies>
<dependency><groupId>org.robolectric</groupId><artifactId>robolectric</artifactId><version>4.17</version></dependency>
<dependency><groupId>org.robolectric</groupId><artifactId>android-all</artifactId><version>14-robolectric-10818077</version></dependency>
<dependency><groupId>junit</groupId><artifactId>junit</artifactId><version>4.13.2</version></dependency>
</dependencies></project>
'''



def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap_dexkit(out):
    """Reuse verified public API acquisition; only transport may retry."""
    return acquire(DEFAULT_CACHE, out / 'dexkit-bootstrap.json')


def run(command, log, allow_failure=False):
    with log.open('w') as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=600)
    print(log.name + ': exit=' + str(result.returncode), flush=True)
    if result.returncode and not allow_failure:
        print(log.read_text()[-18000:])
        raise RuntimeError('Command failed: ' + command[0])
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dexkit', type=Path)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--sdk-jars', type=Path)
    parser.add_argument('--maven', default='mvn')
    parser.add_argument('--maven-repo', type=Path)
    parser.add_argument('--allow-test-failure', action='store_true')
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dexkit = args.dexkit.resolve() if args.dexkit else bootstrap_dexkit(out)
    if digest(dexkit) != DEXKIT_SHA256:
        raise RuntimeError('DexKit 2.2.0 API identity mismatch')
    deps = args.deps.resolve() if args.deps else out / 'deps'
    deps.mkdir(parents=True, exist_ok=True)
    if not args.deps:
        (out / 'pom.xml').write_text(POM)
        command = [args.maven, '-B', '-f', str(out / 'pom.xml'),
                   'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies',
                   '-DoutputDirectory=' + str(deps)]
        if args.maven_repo: command.append('-Dmaven.repo.local=' + str(args.maven_repo.resolve()))
        from maven_dependencies import resolve_dependencies
        resolve_dependencies(command, out / 'dependencies.log', timeout=600)
        for archive in deps.glob('*.aar'):
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if name == 'classes.jar' or (name.startswith('libs/') and name.endswith('.jar')):
                        (deps / (archive.stem + '-' + name.replace('/', '_'))).write_bytes(bundle.read(name))
    compiler = shutil.which('kotlinc')
    if not compiler: raise RuntimeError('Kotlin compiler is required')
    kotlin_runtime = Path(compiler).resolve().parents[1] / 'lib/kotlin-stdlib.jar'
    if not kotlin_runtime.is_file(): raise RuntimeError('Kotlin runtime is missing')
    android = deps / 'android-all-14-robolectric-10818077.jar'
    if not android.is_file(): raise RuntimeError('Pinned compilation Android API is missing')
    classes, stage = out / 'classes', out / 'sources'
    classes.mkdir()
    identities, staged = {}, {}
    for relative in PRODUCTION + [FIXTURE]:
        source = (ROOT if relative == FIXTURE else root) / relative
        dest = stage / relative; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest); staged[relative] = dest; identities[str(relative)] = digest(source)
    for name in ('qa/android_call_recording_audio_test.py',
                 'qa/test_call_recording_lifecycle.py', 'qa/maven_dependencies.py'):
        identities[name] = digest(ROOT / name)
    screen_path = BASE / 'ui/screens/calls/CallsHubScreen.kt'
    screen = (root / screen_path).read_text()
    identities[str(screen_path)] = digest(root / screen_path)
    initial = re.search(r'mutableStateOf\((prefManager\.getBoolean\("call_recording_allow_mic_fallback", (?:true|false)\))\)', screen).group(1)
    start = screen.rindex('onCheckedChange = { enabled ->', 0, screen.index('if (prefManager.putBooleans(mapOf("call_recording_allow_mic_fallback"'))
    opening = screen.index('{', start); depth = 1; end = opening + 1
    while depth:
        depth += (screen[end] == '{') - (screen[end] == '}'); end += 1
    callback = screen[screen.index('->', opening) + 2:end - 1]
    ui_probe = stage / 'CallRecordingSettingsProbe.kt'
    ui_probe.write_text('''package com.waenhancer.xposed.features.media
import android.content.Context
import android.widget.Toast
import com.waenhancer.core.preferences.WaexPreferenceManager
private object R { object string { const val call_recording_setting_save_failed = 1 } }
private object UiText { fun get(id: Int, fallback: String) = fallback }
object CallRecordingSettingsProbe {
 @JvmStatic fun initial(prefManager: WaexPreferenceManager): Boolean = INITIAL
 @JvmStatic fun toggle(prefManager: WaexPreferenceManager, context: Context, previous: Boolean, enabled: Boolean): Boolean {
  var allowMicrophoneFallback = previous
  CALLBACK
  return allowMicrophoneFallback
 }
}
'''.replace('INITIAL', initial).replace('CALLBACK', callback))
    (out / 'source-identity.json').write_text(json.dumps(identities, indent=2) + '\n')
    if len(re.findall(r'@Test\s+public void', staged[FIXTURE].read_text())) * 3 != EXPECTED_TESTS:
        raise RuntimeError('Reviewed fixture method count changed')
    fixtures = []
    for name, content in STUBS.items():
        if not (name.startswith(('de/robv/android/xposed/', 'com/whatsapp/'))
                or name in ('androidx/annotation/NonNull.java', 'androidx/annotation/VisibleForTesting.java',
                            'com/waenhancer/utils/ContactNameResolver.java',
                            'com/waenhancer/xposed/core/devkit/DexSearchEngine.java',
                            'com/waenhancer/xposed/bridge/HookProvider.java')):
            continue
        if name.endswith('DexSearchEngine.java'):
            content = content.replace('return null;', 'throw new AssertionError("Native discovery is outside this fixture");')
        if name.endswith('XposedBridge.java'):
            content = content.replace('public final class XposedBridge {',
                    '''public final class XposedBridge { public static boolean failLog;
 public static void log(Throwable error) { log(error.getClass().getName()); }
 public static java.util.Set<XC_MethodHook.Unhook> hookAllConstructors(Class<?> c,XC_MethodHook h) {
 throw new AssertionError("Constructor hooks are outside this recorder fixture"); }''')
            content = content.replace('public static void reset(){', 'public static void reset(){failLog=false;')
            content = content.replace('public static void log(String s){logs.add(s);}',
                    'public static void log(String s){if(failLog)throw new IllegalStateException("fixture log failure");logs.add(s);}')
        if name.endswith('XposedHelpers.java'):
            if content.count('public class XposedHelpers {') != 1:
                raise RuntimeError('Reviewed Xposed helper boundary changed')
            content = content.replace('public class XposedHelpers {', '''public class XposedHelpers {
 public static XC_MethodHook.Unhook findAndHookMethod(Class<?> c,String n,Object... a) { throw unused(); }
 public static XC_MethodHook.Unhook findAndHookMethod(String c,ClassLoader l,String n,Object... a) { throw unused(); }
 public static Class<?> findClass(String n,ClassLoader l) { throw unused(); }
 public static java.lang.reflect.Field findField(Class<?> c,String n) { throw unused(); }
 public static java.lang.reflect.Field findFieldIfExists(Class<?> c,String n) { throw unused(); }
 public static java.lang.reflect.Method findMethodBestMatch(Class<?> c,String n,Object... a) { throw unused(); }
 public static java.lang.reflect.Method findMethodExact(Class<?> c,String n,Object... a) { throw unused(); }
 public static java.lang.reflect.Method findMethodExactIfExists(Class<?> c,String n,Object... a) { throw unused(); }
 public static Object callMethod(Object o,String n,Object... a) { throw unused(); }
 public static Object getObjectField(Object o,String n) { throw unused(); }
 public static Object getAdditionalInstanceField(Object o,String n) { throw unused(); }
 public static Object setAdditionalInstanceField(Object o,String n,Object v) { throw unused(); }
 public static Object removeAdditionalInstanceField(Object o,String n) { throw unused(); }
 private static AssertionError unused() { return new AssertionError("Unconfigured Xposed helper boundary"); }
''')
        path = stage / 'boundaries' / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content); fixtures.append(path)
    boundaries = {
        'com/waenhancer/xposed/core/privacy/PrivacyPrefs.java': '''package com.waenhancer.xposed.core.privacy;
 public final class PrivacyPrefs { public static int calls;
 public static PrivacyPrefs of(android.content.Context context,android.content.SharedPreferences prefs) {
 calls++; throw new AssertionError("Privacy backend is outside this audio-source fixture"); } }''',
        'com/waenhancer/licensing/customprops/CustomAbPropsStore.java': '''package com.waenhancer.licensing.customprops;
 public interface CustomAbPropsStore { boolean getBoolean(String k,boolean d); void putBoolean(String k,boolean v);
 String getString(String k,String d); void putString(String k,String v); }''',
        'com/waenhancer/config/PreferenceRestartTracker.java': '''package com.waenhancer.config;
 public final class PreferenceRestartTracker { public static int calls;
 public static void onPreferenceChanged(android.content.SharedPreferences prefs,String key) {
 if(!"call_recording_allow_mic_fallback".equals(key))throw new AssertionError("Unexpected restart key");
 calls++; } }''',
        'com/waenhancer/utils/DiagnosticsRecorder.java': '''package com.waenhancer.utils;
 public final class DiagnosticsRecorder { public static int calls;
 public static void recordPreferenceChange(android.content.Context context,String key,boolean scoped,String operation) {
 if(!"call_recording_allow_mic_fallback".equals(key)||scoped||!"PUT".equals(operation))throw new AssertionError("Unexpected diagnostic operation");
 calls++; }
 public static void recordSettingsTransfer(android.content.Context c,String op,int count) {throw new AssertionError("Unexpected settings transfer");} }''',
    }
    for name, content in boundaries.items():
        path = stage / 'boundaries' / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content); fixtures.append(path)
    for name in ('dagger/hilt/android/qualifiers/ApplicationContext', 'androidx/annotation/Nullable'):
        package, annotation = name.rsplit('/', 1)
        path = stage / 'boundaries' / (name + '.java')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('package ' + package.replace('/', '.') + '; public @interface ' + annotation + ' {}\n')
        fixtures.append(path)
    jars = sorted(deps.glob('*.jar'))
    if not any(re.fullmatch(r'kotlin-stdlib-[0-9].*\.jar', p.name) for p in jars): jars.append(kotlin_runtime)
    jars.append(dexkit)
    cp = os.pathsep.join(map(str, jars))
    classpath = str(classes) + os.pathsep + cp
    injection_api = deps / 'javax.inject-1.jar'
    if not injection_api.is_file(): raise RuntimeError('Pinned javax.inject API is missing')
    production_cp = os.pathsep.join(map(str, (classes, android, kotlin_runtime, dexkit, injection_api)))
    run(['javac', '--release', '17', '-cp', production_cp, '-d', str(classes),
         *map(str, fixtures), *[str(staged[p]) for p in JAVA_FIRST]], out / 'javac-fixtures-schema.log')
    run([compiler, '-jvm-target', '17', '-classpath', production_cp, '-d', str(classes),
         *[str(staged[p]) for p in KOTLIN + JAVA_LIFECYCLE]], out / 'kotlinc-base-and-codec.log')
    run(['javac', '--release', '17', '-cp', production_cp, '-d', str(classes),
         *[str(staged[p]) for p in JAVA_LIFECYCLE + JAVA_HOOK]], out / 'javac-recorder.log')
    run([compiler, '-jvm-target', '17', '-classpath', production_cp, '-d', str(classes),
         str(ui_probe)], out / 'kotlinc-settings-fragment.log')
    run(['javac', '--release', '17', '-cp', classpath, '-d', str(classes),
         str(staged[FIXTURE])], out / 'javac-tests.log')
    opens = ['java.base/java.lang', 'java.base/java.util', 'java.base/java.io', 'java.base/java.net',
             'java.base/java.security', 'java.base/java.text', 'java.base/jdk.internal.access',
             'java.desktop/java.awt.font', 'jdk.compiler/com.sun.tools.javac.api']
    command = ['java', *['--add-opens=' + name + '=ALL-UNNAMED' for name in opens],
               '-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2',
               '-cp', classpath, 'org.junit.runner.JUnitCore',
               'com.waenhancer.xposed.features.media.CallRecordingAudioAndroidTest']
    if args.sdk_jars:
        command[1:1] = ['-Drobolectric.offline=true',
                        '-Drobolectric.dependency.dir=' + str(args.sdk_jars.resolve())]
    if args.maven_repo: command.insert(1, '-Dmaven.repo.local=' + str(args.maven_repo.resolve()))
    result = run(command, out / 'junit.log', allow_failure=True)
    log = (out / 'junit.log').read_text()
    success = re.search(r'OK \((\d+) tests?\)', log)
    count = int(success.group(1)) if success else None
    dependencies = {p.name: digest(p) for p in jars}
    if args.sdk_jars: dependencies.update({p.name: digest(p) for p in args.sdk_jars.resolve().glob('*.jar')})
    (out / 'dependency-sha256.json').write_text(json.dumps(dependencies, indent=2) + '\n')
    summary = {'source_root': str(root), 'junit_exit_code': result, 'passed_tests': count,
               'expected_tests': EXPECTED_TESTS, 'methods_per_sdk': 27, 'sdk': [24, 28, 34],
               'source_sha256': identities,
               'limits': 'Complete production recorder, event contract, BaseFeature, HookRegistrar/ViewHookDispatcher, HookErrors, RecordingOutputFiles, preference schema/stores/exclusivity, manager and backup codec. Real Android SharedPreferences, Bundle, ContentResolver and ParcelFileDescriptor on Robolectric 24/28/34. Native media uses an explicit shadow; no audio or encoded bytes. Host, Xposed, scheduler, storage authorization and native DexKit discovery are fixtures. Restart/diagnostic sinks validate and count the expected preference operation, without implementing those subsystems. Only four public CustomAbPropsStore signatures are represented; no private licensing behavior is implemented or tested. Preference failure uses an explicit Context/Editor proxy. Real DexKit 2.2.0 API compilation. No full Compose render, module APK, root, device routing or real call acceptance.'}
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not args.allow_test_failure and (result or count != EXPECTED_TESTS):
        raise RuntimeError('Call audio regression gate failed')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
