#!/usr/bin/env python3
"""Compile real media quality hook/selector contracts against explicit Android/Xposed/DexKit boundaries.

Assertions cover image quality, FPS, the gallery presentation flag, unrelated
host eligibility, invalid method/field contracts, live preferences, exceptions,
and registration idempotence. The host APK identity and actual DexKit search
are explicit test doubles, not certified real-device behavior.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STUBS = {'android/app/Activity.java': 'package android.app; public class Activity extends android.content.Context {public android.content.Intent '
                              'intent; public android.content.Intent getIntent(){return intent;} public void invalidateOptionsMenu(){}}',
 'android/content/Context.java': 'package android.content; public class Context {public String getPackageName(){return "com.whatsapp";}}',
 'android/content/Intent.java': 'package android.content;\n'
                                'public class Intent {public final java.util.Map<String,Boolean> bools=new java.util.HashMap<>();\n'
                                ' public boolean hasExtra(String key){return bools.containsKey(key);}\n'
                                ' public boolean getBooleanExtra(String key,boolean fallback){return bools.getOrDefault(key,fallback);}}\n',
 'android/content/SharedPreferences.java': 'package android.content;\n'
                                           'public interface SharedPreferences {boolean getBoolean(String key,boolean fallback);\n'
                                           ' default String getString(String key,String fallback){return '
                                           'key.equals("hooking_mode")?"Maximum":fallback;}\n'
                                           ' default boolean contains(String key){return false;}\n'
                                           ' default java.util.Set<String> getStringSet(String key,java.util.Set<String> fallback){return '
                                           'fallback;}\n'
                                           '}',
 'android/os/BaseBundle.java': 'package android.os;\n'
                               'public class BaseBundle {public final java.util.Map<String,Boolean> bools=new java.util.HashMap<>();\n'
                               ' public boolean getBoolean(String key,boolean fallback){return bools.getOrDefault(key,fallback);}}\n',
 'android/os/Bundle.java': 'package android.os; public class Bundle extends BaseBundle {public void putString(String k,String v){} public '
                           'void putLong(String k,long v){}}',
 'androidx/annotation/NonNull.java': 'package androidx.annotation; public @interface NonNull {}',
 'androidx/annotation/VisibleForTesting.java': 'package androidx.annotation; public @interface VisibleForTesting {}',
 'androidx/fragment/app/Fragment.java': 'package androidx.fragment.app; public class Fragment {public android.os.Bundle arguments; public '
                                        'android.app.Activity activity; public android.app.Activity getActivity(){return activity;}}',
 'com/waenhancer/xposed/core/BaseFeature.java': 'package com.waenhancer.xposed.core;\n'
                                                'import android.content.*;\n'
                                                'public abstract class BaseFeature {\n'
                                                ' protected final Context context; protected final ClassLoader classLoader; protected '
                                                'final SharedPreferences prefs;\n'
                                                ' protected BaseFeature(Context c, ClassLoader l, SharedPreferences p) { '
                                                'context=c;classLoader=l;prefs=p; }\n'
                                                ' protected boolean isEnabled(String k, boolean d) { return prefs.getBoolean(k,d); }\n'
                                                ' public void beginHookTracking(){} public void endHookTracking(){} public void '
                                                'unhookAll(){}\n'
                                                ' public abstract void hook() throws Throwable;\n'
                                                ' public abstract String getName();\n'
                                                '}\n',
 'com/waenhancer/xposed/core/devkit/DexSearchEngine.java': 'package com.waenhancer.xposed.core.devkit;\n'
                                                           'import android.content.Context; import java.lang.reflect.Method; import '
                                                           'org.luckypray.dexkit.DexKitBridge;\n'
                                                           'public final class DexSearchEngine {\n'
                                                           ' private static final DexSearchEngine INSTANCE=new DexSearchEngine();\n'
                                                           ' public static DexKitBridge bridge; public static int initializes; public '
                                                           'static RuntimeException failure;\n'
                                                           ' public static DexSearchEngine getInstance(){return INSTANCE;}\n'
                                                           ' public void initialize(Context c){initializes++;if(failure!=null)throw '
                                                           'failure;}\n'
                                                           ' public DexKitBridge getBridge(){return bridge;}\n'
                                                           ' public void acquireLease(){} public void releaseLease(){} public void '
                                                           'close(){}\n'
                                                           ' public Method findMethodWithCache(Context c, ClassLoader l, String k, Query '
                                                           'q) {\n'
                                                           '  if(failure!=null)throw failure;\n'
                                                           '  try { return bridge == null ? null : q.run(bridge,l); }\n'
                                                           '  catch (RuntimeException | Error e) { throw e; }\n'
                                                           '  catch (Throwable e) { throw new IllegalStateException(e); }\n'
                                                           ' }\n'
                                                           ' public Class<?> findClassWithCache(Context c,ClassLoader l,String '
                                                           'k,ClassQuery q) {\n'
                                                           '  if(failure!=null)throw failure;\n'
                                                           '  try{return bridge==null?null:q.run(bridge,l);}\n'
                                                           '  catch(RuntimeException|Error e){throw e;}\n'
                                                           '  catch(Throwable e){throw new IllegalStateException(e);}\n'
                                                           ' }\n'
                                                           ' public interface ClassQuery {Class<?> run(DexKitBridge b,ClassLoader l)throws '
                                                           'Throwable;}\n'
                                                           ' public interface Query { Method run(DexKitBridge b, ClassLoader l) throws '
                                                           'Throwable; }\n'
                                                           '}\n',
 'com/waenhancer/xposed/features/customization/PropsOverrideHook.java': 'package com.waenhancer.xposed.features.customization;\n'
                                                                        'import java.util.concurrent.ConcurrentHashMap;\n'
                                                                        'public final class PropsOverrideHook extends '
                                                                        'com.waenhancer.xposed.core.BaseFeature {\n'
                                                                        ' public PropsOverrideHook(android.content.Context c,ClassLoader '
                                                                        'l,android.content.SharedPreferences p){super(c,l,p);}\n'
                                                                        ' public void hook(){throw new AssertionError("Property transport '
                                                                        'outside this fixture");}\n'
                                                                        ' public String getName(){return "Props Override";}\n'
                                                                        ' public static boolean isHookInstalled(){return false;}\n'
                                                                        '\n'
                                                                        ' public static final ConcurrentHashMap<Integer,Boolean> '
                                                                        'BOOLEANS=new ConcurrentHashMap<>();\n'
                                                                        ' public static final ConcurrentHashMap<Integer,Integer> '
                                                                        'INTEGERS=new ConcurrentHashMap<>();\n'
                                                                        ' public static final ConcurrentHashMap<Integer,Float> FLOATS=new '
                                                                        'ConcurrentHashMap<>();\n'
                                                                        ' public static final ConcurrentHashMap<Integer,String> '
                                                                        'STRINGS=new ConcurrentHashMap<>();\n'
                                                                        ' public static void setIntegerOverride(int id,boolean enabled,int '
                                                                        'value) {\n'
                                                                        '  if(enabled)INTEGERS.put(id,value);else INTEGERS.remove(id);\n'
                                                                        ' }\n'
                                                                        ' public static void setBooleanOverride(int id,boolean '
                                                                        'enabled,boolean value) {\n'
                                                                        '  if(enabled)BOOLEANS.put(id,value);else BOOLEANS.remove(id);\n'
                                                                        ' }\n'
                                                                        '}',
 'com/waenhancer/xposed/features/media/MediaHostFingerprint.java': 'package com.waenhancer.xposed.features.media;\n'
                                                                   'public final class MediaHostFingerprint {public static boolean '
                                                                   'accepted=true;public static boolean accepts(android.content.Context '
                                                                   'context){return accepted;}}\n',
 'de/robv/android/xposed/XC_MethodHook.java': 'package de.robv.android.xposed;\n'
                                              'import java.lang.reflect.Method;\n'
                                              'public abstract class XC_MethodHook {\n'
                                              ' protected void beforeHookedMethod(MethodHookParam p) throws Throwable {}\n'
                                              ' protected void afterHookedMethod(MethodHookParam p) throws Throwable {}\n'
                                              ' public final void before(MethodHookParam p) throws Throwable {beforeHookedMethod(p);}\n'
                                              ' public final void after(MethodHookParam p) throws Throwable {afterHookedMethod(p);}\n'
                                              ' public static final class Unhook {public void unhook(){}}\n'
                                              ' public static final class MethodHookParam {\n'
                                              '  public Object thisObject; public Object[] args; public Method method;\n'
                                              '  private Object result; private Throwable throwable;\n'
                                              '  public Object getResult(){return result;}\n'
                                              '  public void setResult(Object v){result=v;throwable=null;}\n'
                                              '  public Throwable getThrowable(){return throwable;}\n'
                                              '  public boolean hasThrowable(){return throwable!=null;}\n'
                                              '  public void setThrowable(Throwable v){throwable=v;result=null;}\n'
                                              ' }\n'
                                              '}\n',
 'de/robv/android/xposed/XposedBridge.java': 'package de.robv.android.xposed;\n'
                                             'import java.lang.reflect.*; import java.util.*;\n'
                                             'public final class XposedBridge {\n'
                                             ' public static final Map<Method,List<XC_MethodHook>> hooks=new LinkedHashMap<>();\n'
                                             ' public static final List<String> logs=new ArrayList<>();\n'
                                             ' public static final Set<Method> rejected=new HashSet<>();\n'
                                             ' public static void log(String s){logs.add(s);}\n'
                                             ' public static void log(Throwable t){logs.add(t.toString());}\n'
                                             ' public static void hookMethod(Method m,XC_MethodHook h){\n'
                                             '  if(rejected.contains(m))throw new '
                                             'IllegalStateException("fixture-private-registration-value");\n'
                                             '  hooks.computeIfAbsent(m,k->new ArrayList<>()).add(h);\n'
                                             ' }\n'
                                             ' public static Set<XC_MethodHook.Unhook> hookAllConstructors(Class<?> c,XC_MethodHook cb){\n'
                                             '  Set<XC_MethodHook.Unhook> results=new LinkedHashSet<>();\n'
                                             '  for(Constructor<?> ctor:c.getDeclaredConstructors())results.add(new '
                                             'XC_MethodHook.Unhook());\n'
                                             '  return results;\n'
                                             ' }\n'
                                             ' public static XC_MethodHook.MethodHookParam invoke(Method m,Object receiver,Object... args) '
                                             'throws Throwable {\n'
                                             '  XC_MethodHook.MethodHookParam p=new '
                                             'XC_MethodHook.MethodHookParam();p.method=m;p.thisObject=receiver;p.args=args;\n'
                                             '  List<XC_MethodHook> list=hooks.getOrDefault(m,Collections.emptyList());\n'
                                             '  for(XC_MethodHook h:list)h.before(p);\n'
                                             '  try {m.setAccessible(true);p.setResult(m.invoke(receiver,p.args));}\n'
                                             '  catch(InvocationTargetException e){p.setThrowable(e.getCause());}\n'
                                             '  for(int i=list.size()-1;i>=0;i--)list.get(i).after(p);\n'
                                             '  return p;\n'
                                             ' }\n'
                                             ' public static int registrations(){return '
                                             'hooks.values().stream().mapToInt(List::size).sum();}\n'
                                             '}\n',
 'org/luckypray/dexkit/DexKitBridge.java': 'package org.luckypray.dexkit;\n'
                                           'import java.lang.reflect.*; import java.util.*;\n'
                                           'import org.luckypray.dexkit.query.*; import org.luckypray.dexkit.query.matchers.*;\n'
                                           'import org.luckypray.dexkit.query.enums.*; import org.luckypray.dexkit.result.*;\n'
                                           'public final class DexKitBridge {\n'
                                           ' public final MethodDataList methods=new MethodDataList(); public final ClassDataList '
                                           'classes=new ClassDataList();\n'
                                           ' public int queries;\n'
                                           ' public MethodData getMethodData(Method method) {for(MethodData '
                                           'd:methods)if(d.method.equals(method))return d;return null;}\n'
                                           ' public MethodData getMethodData(Constructor<?> constructor){return null;}\n'
                                           ' public MethodDataList findMethod(FindMethod q){\n'
                                           '  queries++; MethodDataList result=new MethodDataList();MethodMatcher m=q.matcher;\n'
                                           '  for(MethodData data:methods){\n'
                                           '   Method method=data.method;String[] '
                                           'params=Arrays.stream(method.getParameterTypes()).map(Class::getName).toArray(String[]::new);\n'
                                           '   if(m.returns!=null&&!m.returns.equals(method.getReturnType().getName()))continue;\n'
                                           '   if(m.params!=null&&!Arrays.equals(m.params,params))continue;\n'
                                           '   if(m.count!=null&&m.count!=params.length)continue;\n'
                                           '   if(m.flags!=null&&(method.getModifiers()&m.flags)!=m.flags)continue;\n'
                                           '   boolean matched=true;\n'
                                           '   for(Map.Entry<String,StringMatchType> a:m.strings.entrySet()){\n'
                                           '    boolean any=false;for(String value:data.anchors){\n'
                                           '     switch(a.getValue()){\n'
                                           '      case Equals:any|=value.equals(a.getKey());break;\n'
                                           '      case Contains:any|=value.contains(a.getKey());break;\n'
                                           '      case StartsWith:any|=value.startsWith(a.getKey());break;\n'
                                           '      case EndsWith:any|=value.endsWith(a.getKey());break;\n'
                                           '     }\n'
                                           '    }if(!any){matched=false;break;}\n'
                                           '   }\n'
                                           '   if(matched)result.add(data);\n'
                                           '  }return result;\n'
                                           ' }\n'
                                           ' public ClassDataList findClass(FindClass q){\n'
                                           '  queries++;ClassDataList out=new ClassDataList();\n'
                                           '  for(ClassData data:classes){\n'
                                           '   try{\n'
                                           '    if(q.matcher.iface!=null){Class<?> '
                                           'i=Class.forName(q.matcher.iface);if(i.isAssignableFrom(data.type))out.add(data);}\n'
                                           '    else if(q.matcher.anchor!=null){\n'
                                           '     boolean found=false;for(MethodData '
                                           'method:methods){if(method.method.getDeclaringClass()!=data.type)continue;\n'
                                           '      for(String '
                                           'text:method.anchors){found|=q.matcher.match==StringMatchType.StartsWith?text.startsWith(q.matcher.anchor):text.equals(q.matcher.anchor);}}\n'
                                           '     if(found)out.add(data);\n'
                                           '    }\n'
                                           '   }\n'
                                           '   catch(ClassNotFoundException e){throw new IllegalStateException(e);}\n'
                                           '  }return out;\n'
                                           ' }\n'
                                           '}\n',
 'org/luckypray/dexkit/query/FindClass.java': 'package org.luckypray.dexkit.query;\n'
                                              'import org.luckypray.dexkit.query.matchers.ClassMatcher;\n'
                                              'public final class FindClass {\n'
                                              ' public ClassMatcher matcher;\n'
                                              ' public static FindClass create(){return new FindClass();}\n'
                                              ' public FindClass matcher(ClassMatcher m){matcher=m;return this;}\n'
                                              '}\n',
 'org/luckypray/dexkit/query/FindMethod.java': 'package org.luckypray.dexkit.query;\n'
                                               'import org.luckypray.dexkit.query.matchers.MethodMatcher;\n'
                                               'public final class FindMethod {\n'
                                               ' public MethodMatcher matcher;\n'
                                               ' public static FindMethod create(){return new FindMethod();}\n'
                                               ' public FindMethod matcher(MethodMatcher m){matcher=m;return this;}\n'
                                               '}\n',
 'org/luckypray/dexkit/query/enums/StringMatchType.java': 'package org.luckypray.dexkit.query.enums;\n'
                                                          'public enum StringMatchType {Contains,Equals,StartsWith,EndsWith}\n',
 'org/luckypray/dexkit/query/matchers/ClassMatcher.java': 'package org.luckypray.dexkit.query.matchers;\n'
                                                          'public final class ClassMatcher {\n'
                                                          ' public String iface, anchor; public '
                                                          'org.luckypray.dexkit.query.enums.StringMatchType match;\n'
                                                          ' public static ClassMatcher create(){return new ClassMatcher();}\n'
                                                          ' public ClassMatcher addInterface(String s){iface=s;return this;}\n'
                                                          ' public ClassMatcher addUsingString(String '
                                                          's,org.luckypray.dexkit.query.enums.StringMatchType '
                                                          'type){anchor=s;match=type;return this;}\n'
                                                          '}\n',
 'org/luckypray/dexkit/query/matchers/MethodMatcher.java': 'package org.luckypray.dexkit.query.matchers;\n'
                                                           'import java.util.*; import org.luckypray.dexkit.query.enums.StringMatchType;\n'
                                                           'public final class MethodMatcher {\n'
                                                           ' public final Map<String,StringMatchType> strings=new LinkedHashMap<>();\n'
                                                           ' public String returns; public String[] params; public Integer count,flags;\n'
                                                           ' public static MethodMatcher create(){return new MethodMatcher();}\n'
                                                           ' public MethodMatcher addUsingString(String s,StringMatchType '
                                                           't){strings.put(s,t);return this;}\n'
                                                           ' public MethodMatcher usingStrings(String... ss){for(String '
                                                           's:ss)strings.put(s,StringMatchType.Contains);return this;}\n'
                                                           ' public MethodMatcher paramTypes(Class<?>... '
                                                           'a){params=Arrays.stream(a).map(Class::getName).toArray(String[]::new);return '
                                                           'this;}\n'
                                                           ' public MethodMatcher paramTypes(String... a){params=a;return this;}\n'
                                                           ' public MethodMatcher paramCount(int n){count=n;return this;}\n'
                                                           ' public MethodMatcher returnType(Class<?> c){returns=c.getName();return '
                                                           'this;}\n'
                                                           ' public MethodMatcher returnType(String s){returns=s;return this;}\n'
                                                           ' public MethodMatcher modifiers(int f){flags=f;return this;}\n'
                                                           '}\n',
 'org/luckypray/dexkit/result/ClassData.java': 'package org.luckypray.dexkit.result;\n'
                                               'public class ClassData { public final Class<?> type; public ClassData(Class<?> '
                                               'c){type=c;}\n'
                                               ' public Class<?> getInstance(ClassLoader l) throws ReflectiveOperationException {return '
                                               'type;}}\n',
 'org/luckypray/dexkit/result/ClassDataList.java': 'package org.luckypray.dexkit.result;\n'
                                                   'public class ClassDataList extends java.util.ArrayList<ClassData> { public ClassData '
                                                   'firstOrNull(){return isEmpty()?null:get(0);} }\n',
 'org/luckypray/dexkit/result/FieldData.java': 'package org.luckypray.dexkit.result;\n'
                                               'import java.lang.reflect.Field;\n'
                                               'public class FieldData { private final Field f; public FieldData(Field f){this.f=f;}\n'
                                               ' public Field getFieldInstance(ClassLoader l) throws ReflectiveOperationException {return '
                                               'f;}}\n',
 'org/luckypray/dexkit/result/MethodData.java': 'package org.luckypray.dexkit.result;\n'
                                                'import java.lang.reflect.*; import java.util.*;\n'
                                                'public class MethodData {\n'
                                                ' public final Method method; public final List<String> anchors= new ArrayList<>();\n'
                                                ' public final MethodDataList invokes=new MethodDataList();\n'
                                                ' public final List<UsingFieldData> fields=new ArrayList<>();\n'
                                                ' public MethodData(Method m,String... s){method=m;anchors.addAll(Arrays.asList(s));}\n'
                                                ' public Method getMethodInstance(ClassLoader l) throws ReflectiveOperationException '
                                                '{return method;}\n'
                                                ' public boolean isMethod(){return true;}\n'
                                                ' public boolean isConstructor(){return false;}\n'
                                                ' public java.lang.reflect.Constructor<?> getConstructorInstance(ClassLoader l)throws '
                                                'ReflectiveOperationException{throw new NoSuchMethodException("No constructor metadata in '
                                                'this boundary");}\n'
                                                ' public MethodDataList getInvokes(){return invokes;}\n'
                                                ' public List<UsingFieldData> getUsingFields(){return fields;}\n'
                                                ' public List<String> getUsingStrings(){return anchors;}\n'
                                                ' public final java.util.List<Integer> opcodes=new java.util.ArrayList<>();\n'
                                                ' public java.util.List<Integer> getOpCodes(){return opcodes;}\n'
                                                '}\n',
 'org/luckypray/dexkit/result/MethodDataList.java': 'package org.luckypray.dexkit.result;\n'
                                                    'public class MethodDataList extends java.util.ArrayList<MethodData> {\n'
                                                    ' public MethodData firstOrNull(){return isEmpty()?null:get(0);}\n'
                                                    '}\n',
 'org/luckypray/dexkit/result/UsingFieldData.java': 'package org.luckypray.dexkit.result;\n'
                                                    'import java.lang.reflect.Field;\n'
                                                    'public class UsingFieldData { private final FieldData f; public UsingFieldData(Field '
                                                    'f){this.f=new FieldData(f);}\n'
                                                    ' public FieldData getField(){return f;}}\n'}

PRODUCTION = (
    "app/src/main/java/com/waenhancer/xposed/features/media/MediaQualityBypassHook.java",
    "app/src/main/java/com/waenhancer/xposed/features/media/MediaQualitySelectorContract.java",
    "app/src/main/java/com/waenhancer/xposed/features/media/ProcessImageQualityContract.java",
    "app/src/main/java/com/waenhancer/xposed/core/devkit/HookReturnTypeGuard.java",
)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,default=ROOT)
    args=parser.parse_args()
    root=args.source_root.resolve()
    production=[root/f for f in PRODUCTION]
    if any(not f.is_file() for f in production):
        parser.error("Required real production source missing; fixture cannot substitute")
    fixture=ROOT/"qa/fixtures/media_quality/MediaQualityContractTest.java"
    with tempfile.TemporaryDirectory(prefix="waex_media_quality_") as tmp:
        out=Path(tmp)
        stubs=[]
        for name,contents in STUBS.items():
            f=out/name;f.parent.mkdir(parents=True,exist_ok=True)
            f.write_text(contents,encoding="utf8");stubs.append(f)
        test=out/"MediaQualityContractTest.java"
        test.write_text(fixture.read_text(encoding="utf8"),encoding="utf8")
        compile=subprocess.run(["javac","--release","17","-encoding","UTF-8","-d",str(out),
            *map(str,stubs),*map(str,production),str(test)],
            capture_output=True,text=True,timeout=90)
        if compile.returncode:
            print(compile.stdout+compile.stderr,flush=True)
            raise SystemExit("Real media quality hook/contract compilation failed")
        result=subprocess.run(["java","-cp",str(out),"MediaQualityContractTest"],
            capture_output=True,text=True,timeout=60)
        print(result.stdout,flush=True)
        if result.returncode:
            print(result.stderr,flush=True)
            raise SystemExit("Compiled media quality behavioral suite failed")
        match=re.search(r"RESULT checks=(\d+) failures=(\d+) suite=media",result.stdout)
        if not match or int(match.group(1))<30 or int(match.group(2))!=0:
            raise SystemExit("Missing/incomplete media-quality assertion matrix")
        print("PASS compiled media quality; checks="+match.group(1),flush=True)
        # Independently compile the real APK fingerprint policy, never its test double.
        fingerprint=root/"app/src/main/java/com/waenhancer/xposed/features/media/MediaHostFingerprint.java"
        if not fingerprint.is_file():
            raise SystemExit("Real MediaHostFingerprint.java absent")
        native=out/"fingerprint";native.mkdir()
        context=native/"Context.java"
        context.write_text("package android.content; public class Context {"
            "public String getPackageName(){return \"com.whatsapp\";}"
            "public android.content.pm.ApplicationInfo getApplicationInfo(){"
            "android.content.pm.ApplicationInfo x=new android.content.pm.ApplicationInfo();"
            "x.sourceDir=\"/missing-waex-host-apk\";return x;}}",encoding="utf8")
        app=native/"ApplicationInfo.java"
        app.write_text("package android.content.pm; public class ApplicationInfo {public String sourceDir;}",encoding="utf8")
        probe=native/"FingerprintProbe.java"
        probe.write_text("package com.waenhancer.xposed.features.media;"
            "public class FingerprintProbe {public static void main(String[] x)throws Exception{"
            "java.io.File f=java.io.File.createTempFile(\"invalid-host-\",\".apk\");"
            "try{if(MediaHostFingerprint.accepts(null)||MediaHostFingerprint.accepts(new android.content.Context())"
            "||MediaHostFingerprint.acceptsFile(\"com.whatsapp\",null)"
            "||MediaHostFingerprint.acceptsFile(\"com.whatsapp\",f)"
            "||MediaHostFingerprint.acceptsFile(\"another.host\",f))"
            "throw new AssertionError(\"APK identity was accepted without a matching signed host\");"
            "System.out.println(\"PASS real fingerprint: 5 invalid-host cases rejected\");}"
            "finally{if(!f.delete())throw new AssertionError(\"fixture cleanup failed\");}}}",encoding="utf8")
        compiled=subprocess.run(["javac","--release","17","-d",str(native),str(context),str(app),str(probe),str(fingerprint)],
            capture_output=True,text=True,timeout=60)
        if compiled.returncode:
            print(compiled.stdout+compiled.stderr,flush=True)
            raise SystemExit("Real fingerprint source compilation failed")
        checked=subprocess.run(["java","-cp",str(native),"com.waenhancer.xposed.features.media.FingerprintProbe"],
            capture_output=True,text=True,timeout=30)
        if checked.returncode:
            print(checked.stdout+checked.stderr,flush=True)
            raise SystemExit("Real fingerprint fail-closed tests failed")
        print(checked.stdout.strip(),flush=True)

if __name__=="__main__":main()
