#!/usr/bin/env python3
"""Run literal public MainHook initialization/reporting slices and the complete preference bridge.

Private attach/custom-props integration is excluded, with byte-span receipts; no licensing doubles
or complete MainHook claim. The actual registry report method and dispatcher binding are
also literal; feature installation, JSON, platform, detector and UI boundaries remain.
The retired periodic heartbeat is replaced by the current on-demand hook-report receiver.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from runtime_source_slices import main_hook_slice, registry_reporting_slice

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--main-source', type=Path, default=SRC/'xposed/MainHook.java')
    parser.add_argument('--bridge-source', type=Path, default=SRC/'xposed/bridge/client/PreferenceBridgeClient.java')
    parser.add_argument('--dispatcher-source', type=Path, default=SRC/'xposed/core/RuntimeReportDispatcher.java')
    parser.add_argument('--registry-source', type=Path, default=SRC/'xposed/core/FeatureRegistry.java')
    parser.add_argument('--scenario', default='all', choices=['all','inventory_order','release_callback','package','hooks','update','hook_reports','preferences','initial_sync','interrupted_initial_sync','provider_fallback','unsupported','initialization_failure','fallback','duplicate','optional_failure'])
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    tree = ast.parse((ROOT/'qa/test_bridge_contract.py').read_text())
    stubs = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'STUBS' for t in n.targets)))
    stubs.pop('test/BridgeContract.java')
    stubs.update(SUBSTITUTES)
    ids = sorted(set(re.findall(r'R\.string\.(\w+)', args.main_source.read_text())))
    stubs['com/waenhancer/app/R.java'] = 'package com.waenhancer.app; public final class R { public static final class string { '+''.join(f'public static final int {key}={i};' for i,key in enumerate(ids))+' } }'
    for name, text in stubs.items():
        path = out/'src'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(text.encode('utf-8'))
    fixture = ROOT/'qa/fixtures/InjectionIoRuntimeChecks.java'
    source = out/'src/fixture/InjectionIoRuntimeChecks.java'; source.write_bytes(fixture.read_bytes())
    generated, extraction = main_hook_slice(args.main_source)
    main_path = out/'src/com/waenhancer/xposed/MainHook.java'
    main_path.parent.mkdir(parents=True, exist_ok=True); main_path.write_bytes(generated.encode('utf-8'))
    registry, registry_extraction = registry_reporting_slice(args.registry_source)
    registry_path = out/'src/com/waenhancer/xposed/core/FeatureRegistry.java'
    registry_path.parent.mkdir(parents=True, exist_ok=True); registry_path.write_bytes(registry.encode('utf-8'))
    sources = [args.bridge_source, args.dispatcher_source, SRC/'config/PreferenceSchema.java', SRC/'xposed/utils/HookErrors.java']
    compiled = subprocess.run(['javac','--release','17','-d',str(out/'classes'),
        *map(str, sorted((out/'src').rglob('*.java'))), *map(str,sources)], text=True, capture_output=True, timeout=60)
    (out/'compile.log').write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:
        raise SystemExit('INFRASTRUCTURE_FAILURE: compile; see '+str(out/'compile.log'))
    print('COMPILE_OK: public MainHook/registry report slices and complete preference bridge/dispatcher', flush=True)
    cases = ['inventory_order','release_callback','package','hooks','update','hook_reports','preferences','initial_sync','interrupted_initial_sync','provider_fallback','unsupported',
             'initialization_failure','fallback','duplicate','optional_failure'] if args.scenario == 'all' else [args.scenario]
    results = []
    for case in cases:
        result = subprocess.run(['java','-cp',str(out/'classes'),'fixture.InjectionIoRuntimeChecks',case],
            text=True,capture_output=True,timeout=20)
        (out/(case+'.log')).write_text(result.stdout+result.stderr)
        classification = ('passed' if result.returncode == 0 else 'behavioral_failure') if result.stdout.startswith('RESULT ') else 'infrastructure_failure'
        record = {'scenario':case,'exit':result.returncode,'classification':classification,'output':result.stdout.strip()}
        results.append(record); print(json.dumps(record),flush=True)
    manifest = {'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(), 'results':results, 'extraction':extraction,
        'registry_extraction':registry_extraction,
        'scope':'literal public MainHook initializer/report members and actual registry report method/dispatcher binding; complete PreferenceBridgeClient/dispatcher/schema/HookErrors; explicit platform/detector/feature installation/JSON boundaries; no private implementation, no device benchmark'}
    (out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
    raise SystemExit(1 if any(r['exit'] for r in results) else 0)

SUBSTITUTES = {
 'android/annotation/SuppressLint.java':'package android.annotation; public @interface SuppressLint {String[] value();}',
 'android/content/Context.java':'''package android.content;
import java.util.*;
public abstract class Context {
 public static final int RECEIVER_EXPORTED=2; public static final String CLIPBOARD_SERVICE="clipboard";
 public final Map<String,BroadcastReceiver> receivers=new HashMap<>();
 public Context getApplicationContext(){return this;} public String getPackageName(){return "com.whatsapp";}
 public abstract ContentResolver getContentResolver();
 public Intent registerReceiver(BroadcastReceiver r,IntentFilter f,String permission,android.os.Handler h){receivers.put(f.action,r);return null;}
 public Intent registerReceiver(BroadcastReceiver r,IntentFilter f,String p,android.os.Handler h,int flags){return registerReceiver(r,f,p,h);}
 public Object getSystemService(String name){return null;}
}''',
 'android/content/ContextWrapper.java':'package android.content; public abstract class ContextWrapper extends Context {}',
 'android/content/IntentFilter.java':'package android.content; public class IntentFilter {public final String action;public IntentFilter(String a){action=a;}}',
 'android/content/BroadcastReceiver.java':'package android.content; public abstract class BroadcastReceiver {public abstract void onReceive(Context c,Intent i);}',
 'android/content/Intent.java':'''package android.content;
public class Intent {public String value; public Intent(String a){} public String getStringExtra(String k){return value;}}
''',
 'android/content/ClipboardManager.java':'package android.content; public class ClipboardManager {public void setPrimaryClip(ClipData c){}}',
 'android/content/ClipData.java':'package android.content; public class ClipData {public static ClipData newPlainText(String a,String b){return new ClipData();}}',
 'android/content/DialogInterface.java':'package android.content; public interface DialogInterface {void dismiss(); interface OnClickListener {void onClick(DialogInterface d,int which);}}',
 'android/app/Application.java':'package android.app; public abstract class Application extends android.content.Context {}',
 'android/app/Activity.java':'''package android.app; public abstract class Activity extends android.content.Context {
public boolean isFinishing(){return false;} public boolean isDestroyed(){return false;} public void runOnUiThread(Runnable r){r.run();}}''',
 'android/os/Handler.java':'''package android.os; import java.util.concurrent.*;
public class Handler {public static final BlockingQueue<Runnable> delayed=new LinkedBlockingQueue<>();
public Handler(Looper l){} public boolean post(Runnable r){r.run();return true;}
public boolean postDelayed(Runnable r,long d){delayed.add(r);return true;}}''',
 'android/os/Build.java':'package android.os; public class Build {public static class VERSION {public static int SDK_INT=34;}}',
 'android/os/Process.java':'package android.os; public class Process {public static int killed;public static int myPid(){return 99;}public static void killProcess(int p){killed=p;}}',
 'android/widget/Toast.java':'package android.widget; public class Toast {public static final int LENGTH_SHORT=0;public static Toast makeText(android.content.Context c,String s,int d){return new Toast();}public void show(){}}',
 'de/robv/android/xposed/IXposedHookLoadPackage.java':'package de.robv.android.xposed; public interface IXposedHookLoadPackage {void handleLoadPackage(callbacks.XC_LoadPackage.LoadPackageParam p) throws Throwable;}'.replace('callbacks.XC_LoadPackage','de.robv.android.xposed.callbacks.XC_LoadPackage'),
 'de/robv/android/xposed/IXposedHookZygoteInit.java':'package de.robv.android.xposed; public interface IXposedHookZygoteInit {class StartupParam {public String modulePath;}void initZygote(StartupParam p) throws Throwable;}',
 'de/robv/android/xposed/callbacks/XC_LoadPackage.java':'package de.robv.android.xposed.callbacks; public class XC_LoadPackage {public static class LoadPackageParam {public String packageName,processName;public ClassLoader classLoader;}}',
 'de/robv/android/xposed/XC_MethodHook.java':'''package de.robv.android.xposed;
public abstract class XC_MethodHook {public static class MethodHookParam {public Object thisObject;public Object[] args;public void setResult(Object r){}}
protected void afterHookedMethod(MethodHookParam p)throws Throwable{} protected void beforeHookedMethod(MethodHookParam p)throws Throwable{}
public void runAfter(Object owner,Object...args) {MethodHookParam p=new MethodHookParam();p.thisObject=owner;p.args=args;
try{afterHookedMethod(p);}catch(Throwable t){throw new RuntimeException(t);}}}''',
 'de/robv/android/xposed/XC_MethodReplacement.java':'package de.robv.android.xposed; public abstract class XC_MethodReplacement extends XC_MethodHook {public static XC_MethodHook returnConstant(Object v){return new XC_MethodHook(){};}}',
 'de/robv/android/xposed/XposedHelpers.java':'''package de.robv.android.xposed; import java.util.*;
public class XposedHelpers {public static final Map<String,XC_MethodHook> hooks=new HashMap<>();
public static Object findAndHookMethod(String c,ClassLoader l,String n,Object...a){hooks.put(c+"#"+n,(XC_MethodHook)a[a.length-1]);return null;}}''',
 'de/robv/android/xposed/XposedBridge.java':'package de.robv.android.xposed; public class XposedBridge {public static void log(String s){System.err.println(s);}public static int getXposedVersion(){return 100;}}',
 'de/robv/android/xposed/XSharedPreferences.java':'package de.robv.android.xposed; public class XSharedPreferences extends fixture.TestPrefs {public XSharedPreferences(String p,String n){}public void reload(){}}',
 'fixture/TestPrefs.java':'''package fixture; import java.util.*; import android.content.SharedPreferences;
public class TestPrefs implements SharedPreferences {
 public Map<String,?>getAll(){return Map.of("fresh",false,"show_hook_toast",false);} public boolean getBoolean(String k,boolean d){return false;}
 public String getString(String k,String d){return d;} public Set<String>getStringSet(String k,Set<String>d){return d;}
 public int getInt(String k,int d){return d;} public long getLong(String k,long d){return d;}public float getFloat(String k,float d){return d;}
 public boolean contains(String k){return false;}public void registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l){}
 public void unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l){}
 public Editor edit(){return (Editor)java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(),new Class<?>[]{Editor.class},(p,m,a)->m.getName().equals("commit")?Boolean.TRUE:m.getReturnType()==void.class?null:p);}
}''',
 'com/waenhancer/config/PreferenceStores.java':'package com.waenhancer.config; public class PreferenceStores {public static android.content.SharedPreferences publicStore(android.content.Context c){return new fixture.TestPrefs();}}',
 'com/waenhancer/utils/UiText.java':'package com.waenhancer.utils; public class UiText {public static void initialize(android.content.Context c,android.content.SharedPreferences p){}public static String get(int id,String text){return text;}}',
 'com/waenhancer/utils/WhatsAppPackageDetector.java':'''package com.waenhancer.utils;
import android.content.Context;import android.os.Bundle;import android.net.Uri;
public class WhatsAppPackageDetector {
 public static boolean isWhatsAppPackageName(String p){return "com.whatsapp".equals(p);}
 public static void registerHookedPackage(Context c,String p){c.getContentResolver().call(Uri.parse("content://fixture"),"register_hooked_package",p,null);}
 public static void reportRuntimeHealth(Context c,String p,String status,String bridge,String err){reportRuntimeHealth(c,p,status,bridge,err,System.currentTimeMillis());}
 public static void reportRuntimeHealth(Context c,String p,String status,String bridge,String err,long observed){Bundle b=new Bundle();b.putString("runtime_status",status);b.putString("bridge_status",bridge);b.putLong("timestamp",observed);c.getContentResolver().call(Uri.parse("content://fixture"),"report_runtime_health",p,b);}
}''',
 'com/waenhancer/xposed/utils/TargetExitReporter.java':'''package com.waenhancer.xposed.utils;
public class TargetExitReporter {public static void scheduleOnce(android.content.Context c,String p,boolean consent,long since){if(consent)throw new AssertionError("Exit-history transport is outside the injection-I/O fixture");}}
''',
 'com/waenhancer/xposed/utils/ModuleStatus.java':'package com.waenhancer.xposed.utils; public class ModuleStatus {}',
 'com/waenhancer/xposed/utils/ActivityTracker.java':'''package com.waenhancer.xposed.utils;
public class ActivityTracker {
 public interface ActivityListener {default void onActivityCreated(android.app.Activity a){} void onActivityResumed(android.app.Activity a);default void onActivityStopped(android.app.Activity a){}default void onActivityDestroyed(android.app.Activity a){}}
 public static final java.util.List<ActivityListener> listeners=new java.util.concurrent.CopyOnWriteArrayList<>();
 public static void install(android.app.Application a){} public static void addListener(ActivityListener l){listeners.add(l);}
 public static void removeListener(ActivityListener l){listeners.remove(l);} public static android.app.Activity getCurrentActivity(){return null;}}
''',
 'org/json/JSONObject.java':'package org.json; public class JSONObject extends java.util.LinkedHashMap<String,Object> {}',
 'org/json/JSONArray.java':'''package org.json;
public class JSONArray {private final java.util.List<JSONObject> rows=new java.util.ArrayList<>();
 public void put(JSONObject value){rows.add(value);}public String toString(){return rows.toString();}}
''',
 'com/waenhancer/xposed/core/RestartPromptController.java':'package com.waenhancer.xposed.core;public class RestartPromptController {public static void initialize(android.content.SharedPreferences p){}}',
 'com/waenhancer/xposed/core/VersionGuard.java':'package com.waenhancer.xposed.core;public class VersionGuard {public static boolean allowed=true;public static boolean verifyAndGuard(android.content.Context c,ClassLoader l,android.content.SharedPreferences p){return allowed;}public static String runtimeStatus(){return "UNSUPPORTED_VERSION";}}',
 'com/waenhancer/xposed/features/updates/WhatsAppUpdateSheet.java':'package com.waenhancer.xposed.features.updates;public class WhatsAppUpdateSheet {public static void init(android.content.SharedPreferences p){}}',
 'com/waenhancer/xposed/core/components/WaexBottomSheet.java':'''package com.waenhancer.xposed.core.components;
public class WaexBottomSheet {public WaexBottomSheet(android.app.Activity a){}public WaexBottomSheet asBottomSheet(){return this;}
public WaexBottomSheet setTitle(String s){return this;}public WaexBottomSheet setMessage(String s){return this;}
public WaexBottomSheet setPositiveButton(String s,android.content.DialogInterface.OnClickListener l){return this;}
public WaexBottomSheet setNegativeButton(String s,android.content.DialogInterface.OnClickListener l){return this;}
public void show(){}}
''',
}

if __name__ == '__main__': main()
