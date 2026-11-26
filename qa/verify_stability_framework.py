#!/usr/bin/env python3
"""Isolated real Android/Compose compilation and regressions, not a full WAEX APK.
Modes allow standalone updater/filter/evidence branches without borrowing
production code from another PR. The legacy clock name selects the PID/boot
evidence suite; no periodic clock is reintroduced. Xposed, private Pro behavior
and design theme are fixtures.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, tomllib
import xml.etree.ElementTree as ET
from framework_localization import stage_localization
from gradle_dependencies import PREPARATION_TASK, prepare_dependencies

ROOT = Path(__file__).resolve().parents[1]


def select_modes(mode):
    """Select each canonical suite once; clock is a compatibility alias."""
    if mode == 'all':
        return ['update', 'filter', 'evidence']
    if mode == 'clock':
        return ['evidence']
    if mode in ('update', 'filter', 'evidence'):
        return [mode]
    raise ValueError('Unknown stability mode: '+str(mode))


def selected_modes(mode, root):
    # Upstream 1b029ec88 retired the timer and heartbeat expiry. Its replacement
    # refresh/drain and boot/PID contract runs in test_runtime_observation_clock.py.
    if (root/'app/src/main/java/com/waenhancer/ui/components/RuntimeObservationClock.kt').exists():
        raise ValueError('Retired observation clock reintroduced; review and restore its framework coverage explicitly')
    return select_modes(mode)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--mode',choices=['all','update','filter','evidence','clock'],default='all',
                    help='all runs updater, filter and PID/boot evidence; clock aliases evidence only')
    ap.add_argument('--offline',action='store_true',help='Use the existing Gradle dependency cache only')
    ap.add_argument('--framework-bundle',type=Path,help='Closed 39-file framework bundle from this CI run, attempt and head')
    ap.add_argument('--bundle-run-id');ap.add_argument('--bundle-run-attempt');ap.add_argument('--bundle-head-sha')
    a=ap.parse_args();root=a.root.resolve();out=a.out.resolve()
    try:modes=selected_modes(a.mode,root)
    except ValueError as error:ap.error(str(error))
    origin=(a.bundle_run_id,a.bundle_run_attempt,a.bundle_head_sha)
    if (a.framework_bundle and not all(origin)) or (not a.framework_bundle and any(origin)):
        ap.error('--framework-bundle requires explicit --bundle-run-id, --bundle-run-attempt and --bundle-head-sha')
    if a.framework_bundle:
        import runtime_framework_inputs
        runtime_framework_inputs.identity(*origin)
    out.mkdir(parents=True,exist_ok=False);e=out/'evidence';e.mkdir()
    inputs=None
    if a.framework_bundle:
        inputs=runtime_framework_inputs.prepare(a.framework_bundle,out,*origin,
                    consumer='stability',project='stability-fixture',runner=Path(__file__))
        (e/'framework-inputs-before.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
    p=out/'fixture';p.mkdir();v=tomllib.loads((root/'gradle/libs.versions.toml').read_text())['versions']
    # Compose's BOM does not select the experimental Material3 APIs used by
    # the actual wavy progress indicators. Resolve the *app's* explicit pin.
    app_gradle=(root/'app/build.gradle.kts').read_text()
    expressive_pins=re.findall(r'implementation\("androidx\.compose\.material3:material3:([^"\s]+)"\)',app_gradle)
    if len(expressive_pins)!=1:
        raise ValueError('Expected exactly one explicit app Material3 dependency')
    (p/'settings.gradle.kts').write_text('pluginManagement{repositories{google();mavenCentral();gradlePluginPortal()}}\ndependencyResolutionManagement{repositories{google();mavenCentral()}}\nrootProject.name="stability-fixture"\ninclude(":probe")\n')
    if inputs:
        settings=runtime_framework_inputs.settings(inputs)
        (p/'settings.gradle.kts').write_text(settings,encoding='utf-8')
        (e/'settings.gradle.kts').write_text(settings,encoding='utf-8')
    (p/'gradle.properties').write_text('android.useAndroidX=true\nandroid.builtInKotlin=false\nandroid.newDsl=false\norg.gradle.jvmargs=-Xmx2g\n')
    probe=p/'probe';probe.mkdir()
    def write(path,text):
        f=probe/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
    build='''plugins {
 id("com.android.library") version "AGP"
 id("org.jetbrains.kotlin.android") version "KOTLIN"
 id("org.jetbrains.kotlin.plugin.compose") version "KOTLIN"
}
android {
 namespace="com.waenhancer.app"
 compileSdk=36
 defaultConfig {minSdk=24}
 buildFeatures {compose=true}
 compileOptions {sourceCompatibility=JavaVersion.VERSION_17;targetCompatibility=JavaVersion.VERSION_17}
 kotlinOptions {jvmTarget="17"}
 testOptions {unitTests.isIncludeAndroidResources=true}
}
dependencies {
 implementation(platform("androidx.compose:compose-bom:BOM"))
 implementation("androidx.compose.material3:material3:MATERIAL3")
 implementation("androidx.compose.material:material-icons-extended")
 implementation("androidx.compose.runtime:runtime")
 implementation("androidx.lifecycle:lifecycle-runtime-compose:LIFE")
 implementation("androidx.lifecycle:lifecycle-runtime-ktx:LIFE")
 implementation("androidx.core:core-ktx:CORE")
 implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:CORO")
 implementation("com.squareup.okhttp3:okhttp:OKHTTP")
 testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:CORO")
 testImplementation("org.robolectric:robolectric:4.17")
 testImplementation("junit:junit:4.13.2")
}
'''
    for key,val in {'AGP':v['androidGradlePlugin'],'KOTLIN':v['kotlin'],'BOM':v['androidxComposeBom'],'MATERIAL3':expressive_pins[0],'LIFE':v['androidxLifecycle'],'CORO':v['coroutines'],'CORE':v['androidxCore'],'OKHTTP':v['okhttp']}.items():build=build.replace(key,val)
    build += PREPARATION_TASK
    if inputs:build='import java.security.MessageDigest\nimport java.io.File\n'+build+runtime_framework_inputs.test_configuration(inputs,e)
    write('build.gradle.kts',build)
    write('src/main/AndroidManifest.xml','<manifest xmlns:android="http://schemas.android.com/apk/res/android"/>')
    identity=dict(inputs['source_sha256']) if inputs else {}
    identity['qa/gradle_dependencies.py']=hashlib.sha256(Path(__file__).with_name('gradle_dependencies.py').read_bytes()).hexdigest()
    identity.update({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('app/build.gradle.kts','gradle/libs.versions.toml')})
    sources={'update':['update/UpdateDownloader.kt','update/UpdateTransferPolicy.kt','update/UpdateDownloadSession.kt','update/ReleaseRepository.kt','update/UpdateChannel.kt','update/ReleaseIndex.kt','ui/components/UpdateDownloadSheet.kt','xposed/utils/RootCommandRunner.java','xposed/utils/HookErrors.java','utils/AndroidUserScope.java',
                       'config/PreferenceStores.java','config/PreferenceSchema.java','ui/components/NetworkErrorSheet.kt','ui/components/WaexModalBottomSheet.kt','ui/components/WaexProgressIndicator.kt',
                       'ui/designsystem/WaexIcons.kt','ui/designsystem/WaexRadius.kt','ui/designsystem/WaexElevation.kt','ui/designsystem/WaexColors.kt'],
             'filter':['xposed/features/customization/FilterItemsHook.kt','xposed/features/customization/LayoutPassThrottle.kt','model/FilterItem.kt','xposed/core/ViewHookDispatcher.java','xposed/utils/HostResourceIds.java','xposed/utils/HookErrors.java'],
             'evidence':['utils/InjectionEvidence.kt']}
    expected={'update':12,'filter':3,'evidence':15}
    for mode in modes:
        for rel in sources[mode]:
            source=root/'app/src/main/java/com/waenhancer'/rel
            target=probe/'src/main/java/com/waenhancer'/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
            identity[str(source.relative_to(root))]=hashlib.sha256(source.read_bytes()).hexdigest()
            if hashlib.sha256(target.read_bytes()).hexdigest()!=identity[str(source.relative_to(root))]:
                raise ValueError('Changed bytes while staging production source: '+rel)
        source=root/('qa/fixtures/Stability'+mode.title()+'Test.kt')
        target=probe/'src/test/java/com/waenhancer/fixture'/source.name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        shutil.copy2(source,e/source.name)
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        identity[str(source.relative_to(root))]=digest
        if any(hashlib.sha256(path.read_bytes()).hexdigest()!=digest for path in (target,e/source.name)):
            raise ValueError('Changed bytes while staging JUnit source or evidence: '+source.name)
    # Only a theme adapter for compilation; no fonts or licensing implementation copied.
    # The updater compiles real radius/elevation tokens; other standalone modes
    # must not require a dependency they do not stage.
    update_theme=(' val radius @Composable get()=WaexRadius()\n val elevation @Composable get()=WaexElevation()' if 'update' in modes else '')
    theme='''package com.waenhancer.ui.designsystem
import androidx.compose.runtime.Composable
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.isSystemInDarkTheme
object WaexTheme {
 val colors @Composable get()=COLOR_EXPRESSION
 val typography @Composable get()=FixtureTypography(MaterialTheme.typography)
EXTRA_UPDATE_TOKENS
}
class FixtureTypography(val t:androidx.compose.material3.Typography){val headlineMd get()=t.headlineMedium;val bodyMd get()=t.bodyMedium}
'''
    # Match the public production color *type*, including the isLight contract.
    # Update mode stages the actual WaexColors.kt, while other modes keep a
    # tiny Material3 facade because they do not stage that production source.
    colors_expr=('if(isSystemInDarkTheme()) darkColors else lightColors' if 'update' in modes else 'MaterialTheme.colorScheme')
    write('src/main/java/com/waenhancer/ui/designsystem/WaexTheme.kt',theme.replace('COLOR_EXPRESSION',colors_expr).replace('EXTRA_UPDATE_TOKENS',update_theme))
    # The actual production RootCommandRunner reports failure through HookErrors.
    # Stage it with an explicit XposedBridge boundary instead of omitting the
    # dependency or weakening cleanup and error diagnostics.
    if 'update' in modes and 'filter' not in modes:
        write('src/main/java/de/robv/android/xposed/XposedBridge.java','''package de.robv.android.xposed;
public final class XposedBridge {
  private XposedBridge() {}
  public static void log(String message) { System.err.println("[QA Xposed log] " + message); }
}
''')
    if 'filter' in modes:
        write('src/main/res/values/ids.xml','<resources><item name="fixture_target" type="id"/><item name="fixture_other" type="id"/></resources>')
        write('src/main/java/com/waenhancer/xposed/core/BaseFeature.kt','''package com.waenhancer.xposed.core
import android.content.*
abstract class BaseFeature(protected val context:Context,protected val classLoader:ClassLoader,protected val prefs:SharedPreferences){abstract val name:String;abstract fun hook();fun isEnabled(k:String,d:Boolean)=prefs.getBoolean(k,d)}
''')
        write('src/main/java/com/waenhancer/licensing/features/FilterItemsProFeature.kt','''package com.waenhancer.licensing.features
object FilterItemsProFeature {fun applyProFilter(view:android.view.View,behavior:String,color:Int,opacity:Int,scale:Float,prefs:android.content.SharedPreferences){error("Private Pro implementation must not execute in this fixture")}}
''')
        write('src/main/java/com/waenhancer/xposed/utils/ActivityTracker.kt','''package com.waenhancer.xposed.utils
object ActivityTracker {interface ActivityListener {fun onActivityResumed(a:android.app.Activity)};fun getCurrentActivity():android.app.Activity?=null;fun addListener(l:ActivityListener){error("No hook installation in fixture")}}
''')
        write('src/main/java/de/robv/android/xposed/XC_MethodHook.java','''package de.robv.android.xposed;
public class XC_MethodHook {public static class MethodHookParam {public Object thisObject,result;public Object[] args;}protected void beforeHookedMethod(MethodHookParam p){}protected void afterHookedMethod(MethodHookParam p){}}
''')
        write('src/main/java/de/robv/android/xposed/XposedBridge.java','''package de.robv.android.xposed;
import java.util.Set;
public class XposedBridge {
 public static void log(String s) {}
 public static Set<Object> hookAllMethods(Class<?> cls,String method,XC_MethodHook hook) {
  throw new AssertionError("Unexpected actual Xposed method installation in test fixture");
 }
}''')
        write('src/main/java/de/robv/android/xposed/XposedHelpers.java','''package de.robv.android.xposed;
public class XposedHelpers {public static void findAndHookMethod(Object... args){throw new AssertionError("No actual hooks in this fixture");} public static Object callMethod(Object o,String n,Object... a){throw new AssertionError("Unexpected reflective hook");}public static Object getAdditionalInstanceField(Object o,String n){return null;}public static void setAdditionalInstanceField(Object o,String n,Object v){}}
''')
    if not stage_localization(root, probe, identity):
        raise RuntimeError('Real localization helpers are required by this framework fixture')
    (e/'source-sha256.json').write_text(json.dumps(identity,indent=2));(e/'build.gradle.kts').write_text(build)
    # On Windows, resolve the intended Git Bash rather than System32/WSL bash.
    # Slash paths also preserve Gradle wrapper APP_HOME handling on Git Bash.
    bash=shutil.which('bash')
    if not bash:raise RuntimeError('Compatible bash required for Gradle wrapper')
    prepare_dependencies(root/'gradlew',p,e/'gradle-dependencies.log',bash=bash,offline=a.offline)
    # Never retry compilation/tests. Preserve the caller's mode: AGP may
    # resolve additional tool inputs lazily after the classpath preparation.
    cmd=[bash,(root/'gradlew').as_posix(),'-p',str(p),'--no-daemon',':probe:testDebugUnitTest']
    if a.offline:cmd.append('--offline')
    with (e/'framework-build.log').open('w') as log:
        result=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    for f in (probe/'build/test-results/testDebugUnitTest').glob('*.xml'):shutil.copy2(f,e/f.name)
    reports=list(e.glob('TEST-*.xml'));counts=[0,0,0,0]
    for f in reports:
        t=ET.parse(f).getroot()
        for i,k in enumerate(['tests','failures','errors','skipped']):counts[i]+=int(t.get(k,0))
    summary={'modes':modes,'tests':counts[0],'failures':counts[1],'errors':counts[2],'skipped':counts[3],'build_returncode':result.returncode,'limits':'Real Android Resources/Views/Handler and real Compose Composition/Recomposer; design theme, BaseFeature, Xposed and private Pro service are controlled fixtures, not full WAEX or LSPosed.'}
    (e/'result.json').write_text(json.dumps(summary,indent=2))
    if result.returncode or counts != [sum(expected[m] for m in modes),0,0,0]:
        print((e/'framework-build.log').read_text()[-22000:]);raise RuntimeError('Stability framework failed: '+str(summary))
    if inputs:runtime_framework_inputs.finish(inputs,e)
    print('PASS: '+json.dumps(summary))
if __name__=='__main__':main()
