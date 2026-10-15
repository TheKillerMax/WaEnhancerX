#!/usr/bin/env python3
"""Compile production decision/evidence/inspector/presentation code with explicit Android doubles.

This does not execute root on Android, Compose, Binder, HMA or LSPosed. The shell
command is additionally exercised using a fake pidof executable on the local OS.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'app/src/main/java/com/waenhancer'

def main():
    for tool in ('kotlinc', 'java', 'sh'):
        if not shutil.which(tool):
            raise SystemExit('Required tool unavailable: ' + tool)
    with tempfile.TemporaryDirectory(prefix='waex-runtime-') as temp:
        out = Path(temp); src = out / 'src'; src.mkdir()
        hashes = {}
        def put(name, text):
            (src / name).write_text(text)
        for name in ('UniversalVersionValidator', 'InjectionEvidence', 'TargetRuntimePresentation', 'XposedRuntimeInspector'):
            path = JAVA / ('utils/' + name + '.kt')
            put(name + '.kt', path.read_text())
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        det = (JAVA / 'utils/WhatsAppPackageDetector.kt').read_text()
        model = det[det.index('data class InjectedHookItem('):det.index('object WhatsAppPackageDetector')]
        put('Model.kt', 'package com.waenhancer.utils\n' + model)
        # Full production guard is compiled too; the visual builder is an explicit double.
        put('VersionGuard.kt', (JAVA/'xposed/core/VersionGuard.kt').read_text())
        put('Resources.kt', '''package android.content.res
class Resources(val owner:String,val names:Map<String,Int>,val arrays:Map<Int,Array<String>>,val overrideName:String?=null) {
 class NotFoundException:RuntimeException()
 val reads=mutableListOf<Int>()
 fun getIdentifier(name:String,type:String,pkg:String):Int=if(pkg==owner&&type=="array") names[name]?:0 else 0
 fun getResourceName(id:Int):String=overrideName?:names.entries.firstOrNull{it.value==id}?.let{"$owner:array/${it.key}"}?:throw NotFoundException()
 fun getStringArray(id:Int):Array<String>{reads.add(id);return arrays[id]?.clone()?:throw NotFoundException()}
}
''')
        put('Context.kt', '''package android.content
import android.content.res.Resources
import android.content.pm.PackageManager
open class Context(val packageName:String,val resources:Resources,val module:Context?=null) {
 val packageManager=PackageManager()
 open fun createPackageContext(name:String,flags:Int):Context=module?:throw PackageManager.NameNotFoundException()
 companion object {const val CONTEXT_IGNORE_SECURITY=2}
}
class Intent {fun setClassName(a:String,b:String){};fun putExtra(a:String,b:String){};fun addFlags(f:Int){}
 companion object {const val FLAG_ACTIVITY_NEW_TASK=1;const val FLAG_ACTIVITY_CLEAR_TOP=2;const val FLAG_ACTIVITY_SINGLE_TOP=4}}
interface SharedPreferences {fun getBoolean(k:String,d:Boolean):Boolean;fun getString(k:String,d:String?):String?;fun getStringSet(k:String,d:Set<String>?):Set<String>?;fun edit():Editor
 interface Editor{fun putBoolean(k:String,v:Boolean):Editor;fun putString(k:String,v:String?):Editor;fun putStringSet(k:String,v:Set<String>):Editor;fun apply()}}
''')
        put('PM.kt', '''package android.content.pm
import android.content.Intent
class PackageInfo(val versionName:String?)
class PackageManager {class NameNotFoundException:Exception();var version:String?="2.26.40.76";var fail=false
 fun getPackageInfo(p:String,f:Int):PackageInfo=if(fail)throw NameNotFoundException() else PackageInfo(version)
 fun getLaunchIntentForPackage(p:String):Intent?=Intent()}
''')
        put('Activity.kt', '''package android.app
import android.content.*
import android.content.res.Resources
class Activity:Context("com.whatsapp",Resources("com.whatsapp",emptyMap(),emptyMap())) {
 var isFinishing=false;var isDestroyed=false
 fun runOnUiThread(r:()->Unit)=r();fun startActivity(i:Intent){}
}
''')
        put('Sheet.kt', '''package com.waenhancer.xposed.core.components
import android.app.Activity
class Dialog{fun dismiss(){}}
class WaexBottomSheet(a:Activity) {
 fun setTitle(s:String)=this;fun setMessage(s:String)=apply{lastMessage=s}
 fun setPositiveButton(s:String,f:(Dialog,Int)->Unit)=this
 fun show(){if(fail)throw IllegalStateException();shows++}
 companion object{var fail=false;var shows=0;var lastMessage=""}}
''')
        put('Log.kt', '''package de.robv.android.xposed
object XposedBridge{val logs=mutableListOf<String>();fun log(s:String){logs.add(s)}}
''')
        put('Clock.kt', '''package android.os
object SystemClock{var time=1000L;fun elapsedRealtime()=time}
''')
        put('R.kt', '''package com.waenhancer.app
object R{object array{const val universal_supported_versions=0x7f030000}}
''')
        put('Root.kt', '''package com.waenhancer.xposed.utils
object AppRestartHelper {var output:String?=null;var lastCommand="";var fail=false;var calls=0
 fun runRootCommand(command:String):String?{calls++;lastCommand=command;if(fail)throw SecurityException("secret diagnostic");return output}}
''')
        fixture = (ROOT/'qa/fixtures/RuntimeDiagnosticsChecks.kt').read_text()
        rules=[i.text for i in ET.parse(ROOT/'app/src/main/res/values/arrays.xml').getroot().find("string-array[@name='universal_supported_versions']")]
        put('Checks.kt',fixture.replace('/*BUILTIN_RULES*/',','.join(json.dumps(s) for s in rules)))
        args = [shutil.which('kotlinc'), '-nowarn', '-language-version', '2.0', *map(str, sorted(src.glob('*.kt'))), '-include-runtime', '-d', str(out/'checks.jar')]
        subprocess.run(args, check=True, timeout=90)
        subprocess.run(['java','-jar',str(out/'checks.jar'),str(out/'command.sh')], check=True, timeout=30)
        # Validate the exact emitted shell: unavailable/malformed command results
        # must never produce a valid empty observation. Never invoke real su here.
        command=(out/'command.sh').read_text()
        pidof=out/'pidof';pidof.write_text('#!/bin/sh\nprintf "%s" "$FAKE_OUTPUT"\nexit "$FAKE_CODE"\n');pidof.chmod(0o700)
        for code,output,success in ((0,'123 456',True),(1,'',True),(0,'',False),(1,'123',False),(2,'',False),(127,'',False)):
            env=os.environ|{'PATH':str(out),'FAKE_CODE':str(code),'FAKE_OUTPUT':output}
            result=subprocess.run(['/bin/sh','-c',command],text=True,capture_output=True,env=env,timeout=5)
            assert (result.returncode==0)==success,(code,output,result)
            if success: assert result.stdout==f'PID|com.whatsapp|{output}\n'
        empty=out/'empty';empty.mkdir()
        result=subprocess.run(['/bin/sh','-c',command],text=True,capture_output=True,env=os.environ|{'PATH':str(empty)},timeout=5)
        assert result.returncode==127
    # Guard actual call sites: production decisions, not a replacement demo UI.
    dash=(JAVA/'ui/screens/dashboard/MainDashboardScreen.kt').read_text()
    health=(JAVA/'ui/screens/settings/SystemHealthScreen.kt').read_text()
    versions=(JAVA/'ui/screens/settings/SupportedVersionsScreen.kt').read_text()
    for ui in (dash,health):
        assert 'runtimeSnapshot = refreshed' in ui
        assert 'refreshed ?: XposedRuntimeSnapshot' not in ui
        assert 'rememberRuntimeObservationClock()' in ui and 'TargetRuntimePresentation.asOf(' in ui
    assert 'TargetRuntimePresentation.card(' in dash and 'TargetRuntimePresentation.summarize(' in dash
    assert 'TargetRuntimePresentation.bridge(app)' in health and 'TargetRuntimePresentation.initialization(app)' in health
    assert 'app.injectionEvidence.label' in health
    assert 'UniversalVersionValidator.evaluate(' in versions and 'Version check unavailable' in versions
    assert 'if (isAllSupported)' not in versions
    clock=(JAVA/'ui/components/RuntimeObservationClock.kt').read_text()
    assert 'repeatOnLifecycle(Lifecycle.State.STARTED)' in clock and 'delay(5_000L)' in clock
    assert all(s not in clock for s in ('inspect(', 'detectWhatsAppApps(', 'runRootCommand('))
    assert 'runtimeSnapshot?.pidsFor(' in det and 'classifyInjection(' in det
    assert 'runtimeSnapshot?.runningPids?.get(pkg).orEmpty()' not in det
    mainhook=(JAVA/'xposed/MainHook.java').read_text();provider=(JAVA/'xposed/bridge/HookProvider.java').read_text()
    assert 'VersionGuard.runtimeStatus()' in mainhook and '"COMPATIBILITY_UNAVAILABLE"' in provider
    print('PASS: 7 shell process controls and UI/transport/refresh source guards; no Android/LSPosed test.')
    print('PRODUCTION_SHA256='+json.dumps(hashes,sort_keys=True))

if __name__ == '__main__': main()
