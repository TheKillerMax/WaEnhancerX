#!/usr/bin/env python3
"""Execute exact app listener and provider telemetry spans with full public policy classes.

The private provider/configuration/entitlement and application startup paths are excluded.
No licensing implementation or substitute is compiled. Android persistence, Binder identity,
feature-catalog lookup and optional DiagnosticsRecorder effects are controlled boundaries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from kotlin_compiler import compiler_command
from runtime_source_slices import app_listener_slice, provider_telemetry_slice

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('app/src/main/java/com/waenhancer')
SOURCES = ['xposed/bridge/CallerScopePolicy.java', 'config/PreferenceSyncPolicy.java',
           'config/PreferenceStores.java', 'config/PreferenceSchema.java', 'config/PreferenceRestartTracker.java']
OMITTED_LEGACY_SCENARIOS = ['generic-valid-preference-write',
    'generic-write-disk-failure-keeps-memory-signal', 'privileged-clear-policy',
    'derived-key-and-schema-write-guards', 'entitlement-enforcement-and-refresh']

STUBS = {'android/app/Application.java': 'package android.app;\n'
                                 'public class Application extends android.content.Context { protected void '
                                 'attachBaseContext(android.content.Context base){}public void onCreate(){} }',
 'android/content/ContentProvider.java': 'package android.content;\n'
                                         'import android.net.Uri;import android.os.Bundle;import '
                                         'android.database.Cursor;\n'
                                         'public abstract class ContentProvider {\n'
                                         ' private Context context;public void fixtureAttach(Context '
                                         'c){context=c;}public Context getContext(){return context;}\n'
                                         ' public abstract boolean onCreate();public Bundle call(String method,String '
                                         'arg,Bundle extras){return null;}\n'
                                         ' public abstract Cursor query(Uri uri,String[] projection,String '
                                         'selection,String[] args,String order);\n'
                                         ' public abstract String getType(Uri uri);public abstract Uri insert(Uri '
                                         'uri,ContentValues values);\n'
                                         ' public abstract int delete(Uri uri,String selection,String[] args);public '
                                         'abstract int update(Uri uri,ContentValues values,String selection,String[] '
                                         'args);\n'
                                         '}',
 'android/content/ContentResolver.java': 'package android.content;\n'
                                         'public class ContentResolver { public final java.util.List<String> '
                                         'notifications=new java.util.ArrayList<>();\n'
                                         ' public void notifyChange(android.net.Uri uri,Object '
                                         'observer){notifications.add(uri.toString());} }',
 'android/content/ContentValues.java': 'package android.content; public class ContentValues {}',
 'android/content/Context.java': 'package android.content;\n'
                                 'import java.io.File;import java.util.*;import android.content.pm.*;\n'
                                 'public class Context {\n'
                                 ' public static final int MODE_PRIVATE=0;public final Map<String,FixturePreferences> '
                                 'stores=new HashMap<>();\n'
                                 ' public final ContentResolver resolver=new ContentResolver();public final '
                                 'PackageManager pm=new PackageManager();\n'
                                 ' public final ApplicationInfo info=new ApplicationInfo();public final List<Intent> '
                                 'broadcasts=new ArrayList<>();\n'
                                 ' public SharedPreferences getSharedPreferences(String name,int mode){return '
                                 'stores.computeIfAbsent(name,k->new FixturePreferences());}\n'
                                 ' public ContentResolver getContentResolver(){return resolver;}public PackageManager '
                                 'getPackageManager(){return pm;}\n'
                                 ' public ApplicationInfo getApplicationInfo(){return info;}public String '
                                 'getPackageName(){return "com.waenhancer";}\n'
                                 ' public void sendBroadcast(Intent intent){broadcasts.add(intent);}public File '
                                 'getExternalFilesDir(String type){return null;}\n'
                                 ' public File getFilesDir(){throw new UnsupportedOperationException("Filesystem '
                                 'writes are outside this fixture");}\n'
                                 '}',
 'android/content/FixturePreferences.java': 'package android.content;\n'
                                            'import java.util.*;\n'
                                            '/** Updates memory before persistence; notifies even if commit returns '
                                            'false, like Android. */\n'
                                            'public class FixturePreferences implements SharedPreferences {\n'
                                            ' public final Map<String,Object> values=new LinkedHashMap<>();\n'
                                            ' public final Set<OnSharedPreferenceChangeListener> listeners=new '
                                            'LinkedHashSet<>();\n'
                                            ' public final Deque<Runnable> queued=new ArrayDeque<>();\n'
                                            ' public boolean nextCommit=true,deferred=false;public int '
                                            'edits,commits;public final List<String> changed=new ArrayList<>();\n'
                                            ' public Map<String,?> getAll(){return new LinkedHashMap<>(values);}public '
                                            'boolean contains(String k){return values.containsKey(k);}\n'
                                            ' public String getString(String k,String f){Object v=values.get(k);return '
                                            'v==null?f:(String)v;}\n'
                                            ' @SuppressWarnings("unchecked") public Set<String> getStringSet(String '
                                            'k,Set<String> f){Object v=values.get(k);return v==null?f:new '
                                            'LinkedHashSet<>((Set<String>)v);}\n'
                                            ' public boolean getBoolean(String k,boolean f){Object '
                                            'v=values.get(k);return v==null?f:(Boolean)v;}\n'
                                            ' public int getInt(String k,int f){Object v=values.get(k);return '
                                            'v==null?f:(Integer)v;}\n'
                                            ' public long getLong(String k,long f){Object v=values.get(k);return '
                                            'v==null?f:(Long)v;}\n'
                                            ' public float getFloat(String k,float f){Object v=values.get(k);return '
                                            'v==null?f:(Float)v;}\n'
                                            ' public void '
                                            'registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener '
                                            'l){listeners.add(l);}\n'
                                            ' public void '
                                            'unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener '
                                            'l){listeners.remove(l);}\n'
                                            ' public void notifyKey(String key){changed.add(key);Runnable '
                                            'action=()->{for(var '
                                            'l:List.copyOf(listeners))l.onSharedPreferenceChanged(this,key);};\n'
                                            '  if(deferred)queued.add(action);else action.run();}\n'
                                            ' public void drain(){int '
                                            'guard=0;while(!queued.isEmpty()){if(++guard>10000)throw new '
                                            'AssertionError("Listener loop");queued.remove().run();}}\n'
                                            ' public Editor edit(){edits++;return new Editor(){final '
                                            'Map<String,Object> writes=new LinkedHashMap<>();final Object removed=new '
                                            'Object();boolean clear;\n'
                                            '  public Editor putString(String k,String '
                                            'v){writes.put(k,v==null?removed:v);return this;}\n'
                                            '  public Editor putStringSet(String k,Set<String> '
                                            'v){writes.put(k,v==null?removed:new LinkedHashSet<>(v));return this;}\n'
                                            '  public Editor putInt(String k,int v){writes.put(k,v);return '
                                            'this;}public Editor putLong(String k,long v){writes.put(k,v);return '
                                            'this;}\n'
                                            '  public Editor putFloat(String k,float v){writes.put(k,v);return '
                                            'this;}public Editor putBoolean(String k,boolean v){writes.put(k,v);return '
                                            'this;}\n'
                                            '  public Editor remove(String k){writes.put(k,removed);return '
                                            'this;}public Editor clear(){clear=true;return this;}\n'
                                            '  public boolean commit(){commits++;boolean '
                                            'success=nextCommit;nextCommit=true;List<String> keys=new ArrayList<>();\n'
                                            '   if(clear){values.clear();keys.add(null);}for(var '
                                            'e:writes.entrySet()){String k=e.getKey();Object v=e.getValue();\n'
                                            '    '
                                            'if(v==removed){if(values.containsKey(k)){values.remove(k);keys.add(k);}}\n'
                                            '    else '
                                            'if(!Objects.equals(values.get(k),v)||!values.containsKey(k)){values.put(k,v);keys.add(k);}}\n'
                                            '   for(String key:keys)notifyKey(key);return success;}\n'
                                            '  public void apply(){commit();}\n'
                                            ' };}\n'
                                            '}',
 'android/content/Intent.java': 'package android.content;\n'
                                'public class Intent { public final String action; public String target; public final '
                                'java.util.Map<String,Object> extras=new java.util.HashMap<>();\n'
                                ' public Intent(String action){this.action=action;}public Intent setPackage(String '
                                'target){this.target=target;return this;}\n'
                                ' public Intent putExtra(String key,String value){extras.put(key,value);return this;} '
                                '}',
 'android/content/SharedPreferences.java': 'package android.content;\n'
                                           'import java.util.*;\n'
                                           'public interface SharedPreferences {\n'
                                           ' Map<String,?> getAll();String getString(String key,String '
                                           'fallback);Set<String> getStringSet(String key,Set<String> fallback);\n'
                                           ' int getInt(String key,int fallback);long getLong(String key,long '
                                           'fallback);float getFloat(String key,float fallback);\n'
                                           ' boolean getBoolean(String key,boolean fallback);boolean contains(String '
                                           'key);Editor edit();\n'
                                           ' void '
                                           'registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener '
                                           'listener);\n'
                                           ' void '
                                           'unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener '
                                           'listener);\n'
                                           ' interface OnSharedPreferenceChangeListener { void '
                                           'onSharedPreferenceChanged(SharedPreferences preferences,String key); }\n'
                                           ' interface Editor { Editor putString(String key,String value);Editor '
                                           'putStringSet(String key,Set<String> value);\n'
                                           '  Editor putInt(String key,int value);Editor putLong(String key,long '
                                           'value);Editor putFloat(String key,float value);\n'
                                           '  Editor putBoolean(String key,boolean value);Editor remove(String '
                                           'key);Editor clear();boolean commit();void apply(); }\n'
                                           '}',
 'android/content/pm/ApplicationInfo.java': 'package android.content.pm; public class ApplicationInfo { public int '
                                            'uid=10100; public String dataDir; }',
 'android/content/pm/PackageInfo.java': 'package android.content.pm; public class PackageInfo { public String '
                                        'versionName="fixture-version"; }',
 'android/content/pm/PackageManager.java': 'package android.content.pm;\n'
                                           'public class PackageManager {\n'
                                           ' public final java.util.Map<Integer,String[]> owners=new '
                                           'java.util.HashMap<>();public final java.util.List<Integer> queries=new '
                                           'java.util.ArrayList<>();\n'
                                           ' public String[] getPackagesForUid(int uid){queries.add(uid);return '
                                           'owners.get(uid);}\n'
                                           ' public PackageInfo getPackageInfo(String name,int flags){return new '
                                           'PackageInfo();}\n'
                                           '}',
 'android/database/Cursor.java': 'package android.database; public interface Cursor {}',
 'android/net/Uri.java': 'package android.net;\n'
                         'public final class Uri { final String value; private Uri(String s){value=s;}public static '
                         'Uri parse(String s){return new Uri(s);}\n'
                         ' public String toString(){return value;}public boolean equals(Object o){return o instanceof '
                         'Uri&&value.equals(o.toString());}\n'
                         ' public int hashCode(){return value.hashCode();} }',
 'android/os/Binder.java': 'package android.os;\n'
                           'import java.util.*;\n'
                           'public final class Binder {\n'
                           ' public static int uid=10200,pid=77,clearCount,restoreCount;static long sequence;\n'
                           ' static final Map<Long,int[]> tokens=new HashMap<>();\n'
                           ' public static int getCallingUid(){return uid;}public static int getCallingPid(){return '
                           'pid;}\n'
                           ' public static long clearCallingIdentity(){clearCount++;long '
                           'token=++sequence;tokens.put(token,new int[]{uid,pid});uid=10100;pid=1;return token;}\n'
                           ' public static void restoreCallingIdentity(long token){restoreCount++;int[] '
                           'state=tokens.remove(token);if(state==null)throw new AssertionError("Unknown identity '
                           'token");uid=state[0];pid=state[1];}\n'
                           '}',
 'android/os/Bundle.java': 'package android.os;\n'
                           'import java.util.*;\n'
                           'public class Bundle {\n'
                           ' // Only needed to compile the legacy, unexercised message-store return path.\n'
                           ' public static final Bundle EMPTY=new Bundle();\n'
                           ' public final Map<String,Object> values=new HashMap<>();\n'
                           ' public void putString(String k,String v){values.put(k,v);}public String getString(String '
                           'k){return (String)values.get(k);}\n'
                           ' public String getString(String k,String f){Object v=values.get(k);return '
                           'v==null?f:(String)v;}\n'
                           ' public void putBoolean(String k,boolean v){values.put(k,v);}public boolean '
                           'getBoolean(String k){return getBoolean(k,false);}\n'
                           ' public boolean getBoolean(String k,boolean f){Object v=values.get(k);return '
                           'v==null?f:(Boolean)v;}\n'
                           ' public void putInt(String k,int v){values.put(k,v);}public int getInt(String k){return '
                           'getInt(k,0);}\n'
                           ' public int getInt(String k,int f){Object v=values.get(k);return v==null?f:(Integer)v;}\n'
                           ' public void putLong(String k,long v){values.put(k,v);}public long getLong(String '
                           'k){return getLong(k,0L);}\n'
                           ' public long getLong(String k,long f){Object v=values.get(k);return v==null?f:(Long)v;}\n'
                           ' public void putFloat(String k,float v){values.put(k,v);}public float getFloat(String '
                           'k){Object v=values.get(k);return v==null?0f:(Float)v;}\n'
                           ' public void putParcelable(String k,Object v){values.put(k,v);}public void '
                           'putBundle(String k,Bundle v){values.put(k,v);}\n'
                           ' public Bundle getBundle(String k){return (Bundle)values.get(k);}public void '
                           'putStringArrayList(String k,ArrayList<String> v){values.put(k,v);}\n'
                           ' @SuppressWarnings("unchecked") public ArrayList<String> getStringArrayList(String '
                           'k){return (ArrayList<String>)values.get(k);}\n'
                           ' public void putParcelableArrayList(String k,ArrayList<Bundle> v){values.put(k,v);}\n'
                           ' @SuppressWarnings("unchecked") public ArrayList<Bundle> getParcelableArrayList(String '
                           'k){return (ArrayList<Bundle>)values.get(k);}\n'
                           '}',
 'androidx/annotation/NonNull.java': 'package androidx.annotation; public @interface NonNull {}',
 'androidx/annotation/Nullable.java': 'package androidx.annotation; public @interface Nullable {}',
 'com/waenhancer/config/FeatureCatalog.java': 'package com.waenhancer.config;\n'
                                              'public class FeatureCatalog { public static void '
                                              'initialize(android.content.Context c){}public static Object '
                                              'findByKey(String key){return null;} }',
 'com/waenhancer/utils/DiagnosticsRecorder.java': 'package com.waenhancer.utils;\n'
                                                  'public final class DiagnosticsRecorder {\n'
                                                  ' public static int health,summaries;\n'
                                                  ' public static void reset(){health=0;summaries=0;}\n'
                                                  ' public static void recordHookHealth(android.content.Context '
                                                  'c,String pkg,String status,String bridge,boolean error,int '
                                                  'pid){health++;}\n'
                                                  ' public static void recordHookSummary(android.content.Context '
                                                  'c,String pkg,String hooks){summaries++;}\n'
                                                  '}',
 'com/waenhancer/utils/WhatsAppPackageDetector.java': 'package com.waenhancer.utils;\n'
                                                      'public class WhatsAppPackageDetector { public static final '
                                                      'java.util.Set<String> supported=new '
                                                      'java.util.LinkedHashSet<>();\n'
                                                      ' public static java.util.Set<String> '
                                                      'getSupportedPackages(android.content.Context c){return new '
                                                      'java.util.LinkedHashSet<>(supported);} }'}


def run_contracts(root, out, kotlinc):
    root = root.resolve();out.mkdir(parents=True, exist_ok=True)
    generated, classes = out/'generated', out/'classes'
    generated.mkdir(exist_ok=True); classes.mkdir(exist_ok=True)
    for name, content in STUBS.items():
        path=generated/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(content.encode('utf-8'))
    app_source=root/BASE/'app/WaexApp.kt';provider_source=root/BASE/'xposed/bridge/HookProvider.java'
    app, app_receipt=app_listener_slice(app_source)
    provider, provider_receipt=provider_telemetry_slice(provider_source)
    app_path=generated/'WaexApp.kt';app_path.write_bytes(app.encode('utf-8'))
    provider_path=generated/'com/waenhancer/xposed/bridge/HookProvider.java'
    provider_path.parent.mkdir(parents=True, exist_ok=True);provider_path.write_bytes(provider.encode('utf-8'))
    sources=[root/BASE/name for name in SOURCES]
    stdlib=Path(kotlinc).resolve().parents[1]/'lib/kotlin-stdlib.jar'
    if not stdlib.is_file():raise RuntimeError('Kotlin stdlib absent')
    cp=os.pathsep.join((str(classes),str(stdlib)))
    fixture=ROOT/'qa/fixtures/PreferenceSyncRuntimeChecks.java'
    commands=[['javac','--release','17','-d',str(classes),*map(str,sorted(generated.rglob('*.java'))),*map(str,sources)],
              [*compiler_command(kotlinc),'-jvm-target','17','-classpath',str(classes),'-d',str(classes),str(app_path)],
              ['javac','--release','17','-cp',cp,'-d',str(classes),str(fixture)]]
    with (out/'compile.log').open('w',encoding='utf-8') as log:
        for command in commands:
            result=subprocess.run(command,text=True,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            if result.returncode:raise RuntimeError('INFRASTRUCTURE_FAILURE: compile; '+str(out/'compile.log'))
    print('COMPILE_OK: literal listener/telemetry spans and complete public policies',flush=True)
    xml=ET.parse(root/'app/src/main/res/values/arrays.xml').getroot()
    scopes=[i.text.strip() for a in xml.findall('string-array') if a.attrib.get('name')=='xposed_scope'
            for i in a.findall('item') if i.text and i.text.strip()]
    if not scopes:raise AssertionError('Configured scope absent')
    result=subprocess.run(['java','-ea','-cp',cp,'qa.PreferenceSyncRuntimeChecks',*scopes],text=True,capture_output=True,timeout=60)
    output=result.stdout+result.stderr;(out/'runtime.log').write_bytes(output.encode('utf-8'))
    report={'compile_exit':0,'runtime_exit':result.returncode,'extractions':[app_receipt,provider_receipt],
            'complete_public_sources':{str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
            'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'output':output,
            'omitted_legacy_scenarios':OMITTED_LEGACY_SCENARIOS,'licensing_doubles':False,
            'complete_app_and_provider_compiled':False,'device_instrumentation':False}
    (out/'result.json').write_bytes((json.dumps(report,indent=2)+'\n').encode('utf-8'))
    print(output,end='',flush=True);return result.returncode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--kotlinc',default=os.environ.get('KOTLINC') or shutil.which('kotlinc'))
    args=parser.parse_args()
    if not args.kotlinc:parser.error('Kotlin compiler required')
    if args.out:return run_contracts(args.source_root,args.out,args.kotlinc)
    with tempfile.TemporaryDirectory(prefix='waex-public-preference-sync-') as directory:
        return run_contracts(args.source_root,Path(directory),args.kotlinc)


if __name__=='__main__':raise SystemExit(main())
