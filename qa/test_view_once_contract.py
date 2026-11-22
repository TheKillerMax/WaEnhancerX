#!/usr/bin/env python3
"""Compile the real view-once hook and immutable-message contract with strict host-boundary doubles.

The fixture models message ownership, SQL and direct state setters, live toggles,
ambiguous method/field resolution, Jid hierarchy, and Xposed callback dispatch.
It is not a host/DEX/LSPosed/device acceptance test.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STUBS = {'android/content/Context.java': 'package android.content; public class Context {}',
 'android/content/SharedPreferences.java': 'package android.content;\n'
                                           'public interface SharedPreferences {boolean '
                                           'getBoolean(String key,boolean fallback);\n'
                                           ' default String getString(String key,String '
                                           'fallback){return '
                                           'key.equals("hooking_mode")?"Maximum":fallback;}\n'
                                           ' default boolean contains(String key){return false;}\n'
                                           ' default java.util.Set<String> getStringSet(String '
                                           'key,java.util.Set<String> fallback){return fallback;}\n'
                                           '}',
 'androidx/annotation/NonNull.java': 'package androidx.annotation; public @interface NonNull {}',
 'androidx/annotation/VisibleForTesting.java': 'package androidx.annotation; public @interface '
                                               'VisibleForTesting {}',
 'com/waenhancer/xposed/core/BaseFeature.java': 'package com.waenhancer.xposed.core;\n'
                                                'import android.content.*;\n'
                                                'public abstract class BaseFeature {\n'
                                                ' protected final Context context; protected final '
                                                'ClassLoader classLoader; protected final '
                                                'SharedPreferences prefs;\n'
                                                ' protected BaseFeature(Context c, ClassLoader l, '
                                                'SharedPreferences p) { '
                                                'context=c;classLoader=l;prefs=p; }\n'
                                                ' protected boolean isEnabled(String k, boolean d) { '
                                                'return prefs.getBoolean(k,d); }\n'
                                                ' public void beginHookTracking(){} public void '
                                                'endHookTracking(){} public void unhookAll(){}\n'
                                                ' public abstract void hook() throws Throwable;\n'
                                                ' public abstract String getName();\n'
                                                '}\n',
 'com/waenhancer/xposed/core/devkit/DexSearchEngine.java': 'package com.waenhancer.xposed.core.devkit;\n'
                                                           'import android.content.Context; import '
                                                           'java.lang.reflect.Method; import '
                                                           'org.luckypray.dexkit.DexKitBridge;\n'
                                                           'public final class DexSearchEngine {\n'
                                                           ' private static final DexSearchEngine '
                                                           'INSTANCE=new DexSearchEngine();\n'
                                                           ' public static DexKitBridge bridge; public '
                                                           'static int initializes; public static '
                                                           'RuntimeException failure;\n'
                                                           ' public static DexSearchEngine '
                                                           'getInstance(){return INSTANCE;}\n'
                                                           ' public void initialize(Context '
                                                           'c){initializes++;if(failure!=null)throw '
                                                           'failure;}\n'
                                                           ' public DexKitBridge getBridge(){return '
                                                           'bridge;}\n'
                                                           ' public void acquireLease(){} public void '
                                                           'releaseLease(){} public void close(){}\n'
                                                           ' public Method findMethodWithCache(Context '
                                                           'c, ClassLoader l, String k, Query q) {\n'
                                                           '  if(failure!=null)throw failure;\n'
                                                           '  try { return bridge == null ? null : '
                                                           'q.run(bridge,l); }\n'
                                                           '  catch (RuntimeException | Error e) { '
                                                           'throw e; }\n'
                                                           '  catch (Throwable e) { throw new '
                                                           'IllegalStateException(e); }\n'
                                                           ' }\n'
                                                           ' public Class<?> findClassWithCache(Context '
                                                           'c,ClassLoader l,String k,ClassQuery q) {\n'
                                                           '  if(failure!=null)throw failure;\n'
                                                           '  try{return '
                                                           'bridge==null?null:q.run(bridge,l);}\n'
                                                           '  catch(RuntimeException|Error e){throw '
                                                           'e;}\n'
                                                           '  catch(Throwable e){throw new '
                                                           'IllegalStateException(e);}\n'
                                                           ' }\n'
                                                           ' public interface ClassQuery {Class<?> '
                                                           'run(DexKitBridge b,ClassLoader l)throws '
                                                           'Throwable;}\n'
                                                           ' public interface Query { Method '
                                                           'run(DexKitBridge b, ClassLoader l) throws '
                                                           'Throwable; }\n'
                                                           '}\n',
 'com/whatsapp/infra/core/jid/Jid.java': 'package com.whatsapp.infra.core.jid;\n'
                                         'public class Jid {public String getRawString(){return '
                                         '"fixture@s.whatsapp.net";}}\n',
 'com/whatsapp/infra/core/jid/UserJid.java': 'package com.whatsapp.infra.core.jid;\n'
                                             'public class UserJid extends Jid {}\n',
 'de/robv/android/xposed/XC_MethodHook.java': 'package de.robv.android.xposed;\n'
                                              'import java.lang.reflect.Method;\n'
                                              'public abstract class XC_MethodHook {\n'
                                              ' protected void beforeHookedMethod(MethodHookParam p) '
                                              'throws Throwable {}\n'
                                              ' protected void afterHookedMethod(MethodHookParam p) '
                                              'throws Throwable {}\n'
                                              ' public final void before(MethodHookParam p) throws '
                                              'Throwable {beforeHookedMethod(p);}\n'
                                              ' public final void after(MethodHookParam p) throws '
                                              'Throwable {afterHookedMethod(p);}\n'
                                              ' public static final class Unhook {public void '
                                              'unhook(){}}\n'
                                              ' public static final class MethodHookParam {\n'
                                              '  public Object thisObject; public Object[] args; public '
                                              'Method method;\n'
                                              '  private Object result; private Throwable throwable;\n'
                                              '  public Object getResult(){return result;}\n'
                                              '  public void setResult(Object '
                                              'v){result=v;throwable=null;}\n'
                                              '  public Throwable getThrowable(){return throwable;}\n'
                                              '  public boolean hasThrowable(){return '
                                              'throwable!=null;}\n'
                                              '  public void setThrowable(Throwable '
                                              'v){throwable=v;result=null;}\n'
                                              ' }\n'
                                              '}\n',
 'de/robv/android/xposed/XposedBridge.java': 'package de.robv.android.xposed;\n'
                                             'import java.lang.reflect.*; import java.util.*;\n'
                                             'public final class XposedBridge {\n'
                                             ' public static final Map<Method,List<XC_MethodHook>> '
                                             'hooks=new LinkedHashMap<>();\n'
                                             ' public static final List<String> logs=new '
                                             'ArrayList<>();\n'
                                             ' public static final Set<Method> rejected=new '
                                             'HashSet<>();\n'
                                             ' public static void log(String s){logs.add(s);}\n'
                                             ' public static void log(Throwable '
                                             't){logs.add(t.toString());}\n'
                                             ' public static void hookMethod(Method m,XC_MethodHook '
                                             'h){\n'
                                             '  if(rejected.contains(m))throw new '
                                             'IllegalStateException("fixture-private-registration-value");\n'
                                             '  hooks.computeIfAbsent(m,k->new ArrayList<>()).add(h);\n'
                                             ' }\n'
                                             ' public static Set<XC_MethodHook.Unhook> '
                                             'hookAllConstructors(Class<?> c,XC_MethodHook cb){\n'
                                             '  Set<XC_MethodHook.Unhook> results=new '
                                             'LinkedHashSet<>();\n'
                                             '  for(Constructor<?> '
                                             'ctor:c.getDeclaredConstructors())results.add(new '
                                             'XC_MethodHook.Unhook());\n'
                                             '  return results;\n'
                                             ' }\n'
                                             ' public static XC_MethodHook.MethodHookParam '
                                             'invoke(Method m,Object receiver,Object... args) throws '
                                             'Throwable {\n'
                                             '  XC_MethodHook.MethodHookParam p=new '
                                             'XC_MethodHook.MethodHookParam();p.method=m;p.thisObject=receiver;p.args=args;\n'
                                             '  List<XC_MethodHook> '
                                             'list=hooks.getOrDefault(m,Collections.emptyList());\n'
                                             '  for(XC_MethodHook h:list)h.before(p);\n'
                                             '  try '
                                             '{m.setAccessible(true);p.setResult(m.invoke(receiver,p.args));}\n'
                                             '  catch(InvocationTargetException '
                                             'e){p.setThrowable(e.getCause());}\n'
                                             '  for(int i=list.size()-1;i>=0;i--)list.get(i).after(p);\n'
                                             '  return p;\n'
                                             ' }\n'
                                             ' public static int registrations(){return '
                                             'hooks.values().stream().mapToInt(List::size).sum();}\n'
                                             '}\n',
 'org/luckypray/dexkit/DexKitBridge.java': 'package org.luckypray.dexkit;\n'
                                           'import java.lang.reflect.*; import java.util.*;\n'
                                           'import org.luckypray.dexkit.query.*; import '
                                           'org.luckypray.dexkit.query.matchers.*;\n'
                                           'import org.luckypray.dexkit.query.enums.*; import '
                                           'org.luckypray.dexkit.result.*;\n'
                                           'public final class DexKitBridge {\n'
                                           ' public final MethodDataList methods=new MethodDataList(); '
                                           'public final ClassDataList classes=new ClassDataList();\n'
                                           ' public int queries;\n'
                                           ' public MethodData getMethodData(Method method) '
                                           '{for(MethodData d:methods)if(d.method.equals(method))return '
                                           'd;return null;}\n'
                                           ' public MethodData getMethodData(Constructor<?> '
                                           'constructor){return null;}\n'
                                           ' public MethodDataList findMethod(FindMethod q){\n'
                                           '  queries++; MethodDataList result=new '
                                           'MethodDataList();MethodMatcher m=q.matcher;\n'
                                           '  for(MethodData data:methods){\n'
                                           '   Method method=data.method;String[] '
                                           'params=Arrays.stream(method.getParameterTypes()).map(Class::getName).toArray(String[]::new);\n'
                                           '   '
                                           'if(m.returns!=null&&!m.returns.equals(method.getReturnType().getName()))continue;\n'
                                           '   '
                                           'if(m.params!=null&&!Arrays.equals(m.params,params))continue;\n'
                                           '   if(m.count!=null&&m.count!=params.length)continue;\n'
                                           '   '
                                           'if(m.flags!=null&&(method.getModifiers()&m.flags)!=m.flags)continue;\n'
                                           '   boolean matched=true;\n'
                                           '   for(Map.Entry<String,StringMatchType> '
                                           'a:m.strings.entrySet()){\n'
                                           '    boolean any=false;for(String value:data.anchors){\n'
                                           '     switch(a.getValue()){\n'
                                           '      case Equals:any|=value.equals(a.getKey());break;\n'
                                           '      case Contains:any|=value.contains(a.getKey());break;\n'
                                           '      case '
                                           'StartsWith:any|=value.startsWith(a.getKey());break;\n'
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
                                           '   catch(ClassNotFoundException e){throw new '
                                           'IllegalStateException(e);}\n'
                                           '  }return out;\n'
                                           ' }\n'
                                           '}\n',
 'org/luckypray/dexkit/query/FindClass.java': 'package org.luckypray.dexkit.query;\n'
                                              'import '
                                              'org.luckypray.dexkit.query.matchers.ClassMatcher;\n'
                                              'public final class FindClass {\n'
                                              ' public ClassMatcher matcher;\n'
                                              ' public static FindClass create(){return new '
                                              'FindClass();}\n'
                                              ' public FindClass matcher(ClassMatcher '
                                              'm){matcher=m;return this;}\n'
                                              '}\n',
 'org/luckypray/dexkit/query/FindMethod.java': 'package org.luckypray.dexkit.query;\n'
                                               'import '
                                               'org.luckypray.dexkit.query.matchers.MethodMatcher;\n'
                                               'public final class FindMethod {\n'
                                               ' public MethodMatcher matcher;\n'
                                               ' public static FindMethod create(){return new '
                                               'FindMethod();}\n'
                                               ' public FindMethod matcher(MethodMatcher '
                                               'm){matcher=m;return this;}\n'
                                               '}\n',
 'org/luckypray/dexkit/query/enums/StringMatchType.java': 'package org.luckypray.dexkit.query.enums;\n'
                                                          'public enum StringMatchType '
                                                          '{Contains,Equals,StartsWith,EndsWith}\n',
 'org/luckypray/dexkit/query/matchers/ClassMatcher.java': 'package '
                                                          'org.luckypray.dexkit.query.matchers;\n'
                                                          'public final class ClassMatcher {\n'
                                                          ' public String iface, anchor; public '
                                                          'org.luckypray.dexkit.query.enums.StringMatchType '
                                                          'match;\n'
                                                          ' public static ClassMatcher create(){return '
                                                          'new ClassMatcher();}\n'
                                                          ' public ClassMatcher addInterface(String '
                                                          's){iface=s;return this;}\n'
                                                          ' public ClassMatcher addUsingString(String '
                                                          's,org.luckypray.dexkit.query.enums.StringMatchType '
                                                          'type){anchor=s;match=type;return this;}\n'
                                                          '}\n',
 'org/luckypray/dexkit/query/matchers/MethodMatcher.java': 'package '
                                                           'org.luckypray.dexkit.query.matchers;\n'
                                                           'import java.util.*; import '
                                                           'org.luckypray.dexkit.query.enums.StringMatchType;\n'
                                                           'public final class MethodMatcher {\n'
                                                           ' public final Map<String,StringMatchType> '
                                                           'strings=new LinkedHashMap<>();\n'
                                                           ' public String returns; public String[] '
                                                           'params; public Integer count,flags;\n'
                                                           ' public static MethodMatcher '
                                                           'create(){return new MethodMatcher();}\n'
                                                           ' public MethodMatcher addUsingString(String '
                                                           's,StringMatchType '
                                                           't){strings.put(s,t);return this;}\n'
                                                           ' public MethodMatcher '
                                                           'usingStrings(String... ss){for(String '
                                                           's:ss)strings.put(s,StringMatchType.Contains);return '
                                                           'this;}\n'
                                                           ' public MethodMatcher '
                                                           'paramTypes(Class<?>... '
                                                           'a){params=Arrays.stream(a).map(Class::getName).toArray(String[]::new);return '
                                                           'this;}\n'
                                                           ' public MethodMatcher paramTypes(String... '
                                                           'a){params=a;return this;}\n'
                                                           ' public MethodMatcher paramCount(int '
                                                           'n){count=n;return this;}\n'
                                                           ' public MethodMatcher returnType(Class<?> '
                                                           'c){returns=c.getName();return this;}\n'
                                                           ' public MethodMatcher returnType(String '
                                                           's){returns=s;return this;}\n'
                                                           ' public MethodMatcher modifiers(int '
                                                           'f){flags=f;return this;}\n'
                                                           '}\n',
 'org/luckypray/dexkit/result/ClassData.java': 'package org.luckypray.dexkit.result;\n'
                                               'public class ClassData { public final Class<?> type; '
                                               'public ClassData(Class<?> c){type=c;}\n'
                                               ' public Class<?> getInstance(ClassLoader l) throws '
                                               'ReflectiveOperationException {return type;}}\n',
 'org/luckypray/dexkit/result/ClassDataList.java': 'package org.luckypray.dexkit.result;\n'
                                                   'public class ClassDataList extends '
                                                   'java.util.ArrayList<ClassData> {}\n',
 'org/luckypray/dexkit/result/FieldData.java': 'package org.luckypray.dexkit.result;\n'
                                               'import java.lang.reflect.Field;\n'
                                               'public class FieldData { private final Field f; public '
                                               'FieldData(Field f){this.f=f;}\n'
                                               ' public Field getFieldInstance(ClassLoader l) throws '
                                               'ReflectiveOperationException {return f;}}\n',
 'org/luckypray/dexkit/result/MethodData.java': 'package org.luckypray.dexkit.result;\n'
                                                'import java.lang.reflect.*; import java.util.*;\n'
                                                'public class MethodData {\n'
                                                ' public final Method method; public final List<String> '
                                                'anchors= new ArrayList<>();\n'
                                                ' public final MethodDataList invokes=new '
                                                'MethodDataList();\n'
                                                ' public final List<UsingFieldData> fields=new '
                                                'ArrayList<>();\n'
                                                ' public MethodData(Method m,String... '
                                                's){method=m;anchors.addAll(Arrays.asList(s));}\n'
                                                ' public Method getMethodInstance(ClassLoader l) throws '
                                                'ReflectiveOperationException {return method;}\n'
                                                ' public boolean isMethod(){return true;}\n'
                                                ' public boolean isConstructor(){return false;}\n'
                                                ' public java.lang.reflect.Constructor<?> '
                                                'getConstructorInstance(ClassLoader l)throws '
                                                'ReflectiveOperationException{throw new '
                                                'NoSuchMethodException("No constructor metadata in this '
                                                'boundary");}\n'
                                                ' public MethodDataList getInvokes(){return invokes;}\n'
                                                ' public List<UsingFieldData> getUsingFields(){return '
                                                'fields;}\n'
                                                ' public List<String> getUsingStrings(){return '
                                                'anchors;}\n'
                                                ' public final java.util.List<Integer> opcodes=new '
                                                'java.util.ArrayList<>();\n'
                                                ' public java.util.List<Integer> getOpCodes(){return '
                                                'opcodes;}\n'
                                                '}\n',
 'org/luckypray/dexkit/result/MethodDataList.java': 'package org.luckypray.dexkit.result;\n'
                                                    'public class MethodDataList extends '
                                                    'java.util.ArrayList<MethodData> {\n'
                                                    ' public MethodData firstOrNull(){return '
                                                    'isEmpty()?null:get(0);}\n'
                                                    '}\n',
 'org/luckypray/dexkit/result/UsingFieldData.java': 'package org.luckypray.dexkit.result;\n'
                                                    'import java.lang.reflect.Field;\n'
                                                    'public class UsingFieldData { private final '
                                                    'FieldData f; public UsingFieldData(Field '
                                                    'f){this.f=new FieldData(f);}\n'
                                                    ' public FieldData getField(){return f;}}\n'}

PRODUCTION = (
    "app/src/main/java/com/waenhancer/xposed/features/privacy/AntiViewOnceHook.java",
    "app/src/main/java/com/waenhancer/xposed/features/privacy/ViewOnceMessageContract.java",
    "app/src/main/java/com/waenhancer/xposed/utils/HookErrors.java",
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,default=ROOT)
    parser.add_argument("--jid-family",choices=("modern","legacy"),default="modern")
    args = parser.parse_args()
    source = args.source_root.resolve()
    production = [source/p for p in PRODUCTION]
    if any(not f.is_file() for f in production):
        parser.error("Real production source missing; refusing substitute")
    fixture = ROOT/"qa/fixtures/view_once/ViewOnceContractTest.java"
    if not fixture.is_file():
        parser.error("Focused compiled test fixture missing")
    with tempfile.TemporaryDirectory(prefix="waex_view_once_") as d:
        out=Path(d)
        paths=[]
        for relative, content in STUBS.items():
            if args.jid_family=="legacy" and relative.startswith("com/whatsapp/infra/core/jid/"):
                relative=relative.replace("com/whatsapp/infra/core/jid/","com/whatsapp/jid/")
                content=content.replace("com.whatsapp.infra.core.jid","com.whatsapp.jid")
            dest=out/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(content,encoding="utf8")
            paths.append(dest)
        test=out/"ViewOnceContractTest.java"
        content=fixture.read_text(encoding="utf8")
        if args.jid_family=="legacy":
            content=content.replace("com.whatsapp.infra.core.jid","com.whatsapp.jid")
        test.write_text(content,encoding="utf8")
        javac=subprocess.run(["javac","--release","17","-encoding","UTF-8","-d",str(out),
            *map(str,paths),*map(str,production),str(test)],
            check=False,capture_output=True,text=True,timeout=90)
        if javac.returncode:
            print(javac.stdout+javac.stderr,flush=True)
            raise SystemExit("Real view-once hook/contract compilation failed")
        run=subprocess.run(["java","-cp",str(out),"ViewOnceContractTest"],
            check=False,capture_output=True,text=True,timeout=60)
        print("JID_FAMILY="+args.jid_family,flush=True)
        print(run.stdout,flush=True)
        if run.returncode:
            print(run.stderr,flush=True)
            raise SystemExit("Compiled view-once behavioral suite failed")
        m=re.search(r"RESULT checks=(\d+) failures=(\d+) suite=viewonce",run.stdout)
        if not m or int(m.group(1))<30 or int(m.group(2))!=0:
            raise SystemExit("Missing or incomplete zero-failure view-once suite")
        print("PASS view-once real-source compilation and behavior; checks="+m.group(1),flush=True)

if __name__=="__main__":
    main()
