#!/usr/bin/env python3
"""Compile the complete view-once hook/resolver with explicit Android/host doubles.

Runs real reflection and a real bounded Java executor. This is not Android,
DexKit native discovery, LSPosed, host database execution or MediaStore acceptance.
--dexkit-jar compiles the hook and complete resolvers against the real DexKit API.
--baseline-hook runs a selected regression against an unchanged earlier hook.
"""
from pathlib import Path
import argparse, hashlib, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/com/waenhancer/xposed/features/media'
STUBS = {
'androidx/annotation/NonNull.java': 'package androidx.annotation;public @interface NonNull {}',
'android/content/SharedPreferences.java': 'package android.content;public interface SharedPreferences{boolean getBoolean(String k,boolean d);}',
'android/content/Context.java': '''package android.content;public class Context {
 public Context getApplicationContext(){return this;}public android.content.res.Resources getResources(){return new android.content.res.Resources();}
 public String getPackageName(){return "com.whatsapp";}}''',
'android/content/res/Resources.java': 'package android.content.res;public class Resources{public int getIdentifier(String n,String t,String p){return n.equals("ic_viewonce")?17:0;}}',
'android/app/Activity.java': 'package android.app;public class Activity extends android.content.Context{public java.io.File unrelated;}',
'android/graphics/drawable/Drawable.java': 'package android.graphics.drawable;public class Drawable{}',
'android/os/Looper.java': 'package android.os;public class Looper{public static Looper getMainLooper(){return new Looper();}}',
'android/os/Bundle.java': 'package android.os;public class Bundle{}',
'android/view/View.java': 'package android.view;public class View{}',
'android/os/Handler.java': 'package android.os;public class Handler{public Handler(Looper l){}public boolean post(Runnable r){r.run();return true;}}',
'android/widget/Toast.java': '''package android.widget;import java.util.*;public class Toast{
 public static final int LENGTH_SHORT=0;public static final List<String> shown=Collections.synchronizedList(new ArrayList<>());
 public final String value;public Toast(String s){value=s;}public static Toast makeText(android.content.Context c,String s,int t){return new Toast(s);}
 public void show(){shown.add(value);}}''',
'android/view/MenuInflater.java': 'package android.view;public class MenuInflater{}',
'android/view/Menu.java': '''package android.view;public interface Menu{int NONE=0;MenuItem findItem(int id);
 MenuItem add(int group,int id,int order,CharSequence title);void removeItem(int id);}''',
'android/view/MenuItem.java': '''package android.view;public interface MenuItem{int SHOW_AS_ACTION_ALWAYS=2;
 void setShowAsAction(int action);MenuItem setIcon(android.graphics.drawable.Drawable d);MenuItem setOnMenuItemClickListener(OnMenuItemClickListener l);
 interface OnMenuItemClickListener{boolean onMenuItemClick(MenuItem item);}}''',
'androidx/fragment/app/Fragment.java': 'package androidx.fragment.app;public class Fragment{}',
'androidx/viewpager/widget/ViewPager.java': 'package androidx.viewpager.widget;public class ViewPager{public int index;public int getCurrentItem(){return index;}}',
'com/waenhancer/xposed/core/BaseFeature.java': '''package com.waenhancer.xposed.core;import android.content.*;
 public abstract class BaseFeature{protected final Context context;protected final ClassLoader classLoader;protected final SharedPreferences prefs;
 public BaseFeature(Context c,ClassLoader l,SharedPreferences p){context=c;classLoader=l;prefs=p;}
 protected boolean isEnabled(String k,boolean d){return prefs.getBoolean(k,d);}public abstract void hook()throws Throwable;public abstract String getName();}''',
'com/waenhancer/xposed/features/homescreen/MenuIconLoader.java': '''package com.waenhancer.xposed.features.homescreen;
 public class MenuIconLoader{public static boolean missing;public static android.graphics.drawable.Drawable load(android.content.Context c,String n){return missing?null:new android.graphics.drawable.Drawable();}}''',
'de/robv/android/xposed/XC_MethodHook.java': '''package de.robv.android.xposed;public class XC_MethodHook{
 public class Unhook{private final Runnable action;public Unhook(Runnable r){action=r;}public void unhook(){action.run();}}
 public static class MethodHookParam{public Object thisObject;public Object[] args;public Throwable failure;public Object result=Boolean.TRUE;public Object getResult(){return result;}public boolean hasThrowable(){return failure!=null;}}
 protected void afterHookedMethod(MethodHookParam p)throws Throwable{}public void runAfter(MethodHookParam p)throws Throwable{afterHookedMethod(p);}}''',
'de/robv/android/xposed/XposedBridge.java': '''package de.robv.android.xposed;import java.lang.reflect.*;import java.util.*;
 public class XposedBridge{public static final Map<Method,XC_MethodHook> hooks=new LinkedHashMap<>();public static final List<String> logs=new ArrayList<>();
 public static int installs,failAt,unhooks;public static Error fatal;
 public static XC_MethodHook.Unhook hookMethod(Method m,XC_MethodHook c){if(++installs==failAt){if(fatal!=null)throw fatal;throw new IllegalStateException("/private/fixture-secret-install");}
 hooks.put(m,c);return c.new Unhook(()->{hooks.remove(m,c);unhooks++;});}public static void log(String s){logs.add(s);}}''',
'de/robv/android/xposed/XposedHelpers.java': '''package de.robv.android.xposed;public class XposedHelpers{
 public static Class<?> findClassIfExists(String n,ClassLoader l){try{return Class.forName(n,false,l);}catch(ClassNotFoundException e){return null;}}
 public static void findAndHookMethod(Class<?> c,String n,Object...args)throws Exception{
 Class<?>[] p=new Class<?>[args.length-1];for(int i=0;i<p.length;i++)p[i]=(Class<?>)args[i];
 XposedBridge.hookMethod(c.getMethod(n,p),(XC_MethodHook)args[args.length-1]);}}''',
'com/waenhancer/xposed/core/devkit/DexSearchEngine.java': '''package com.waenhancer.xposed.core.devkit;
 public class DexSearchEngine{private static final DexSearchEngine INSTANCE=new DexSearchEngine();public static org.luckypray.dexkit.DexKitBridge bridge;
 public static DexSearchEngine getInstance(){return INSTANCE;}public void initialize(android.content.Context c){}
 public org.luckypray.dexkit.DexKitBridge getBridge(){return bridge;}
 public interface Query{Class<?> run(org.luckypray.dexkit.DexKitBridge b,ClassLoader l)throws Throwable;}
 public Class<?> findClassWithCache(android.content.Context c,ClassLoader l,String key,Query q)throws Throwable{return q.run(bridge,l);}}''',
'com/waenhancer/xposed/features/media/GalleryMediaExporter.java': '''package com.waenhancer.xposed.features.media;
 import java.io.*;import java.util.*;import java.util.concurrent.*;
 public class GalleryMediaExporter {public static final List<File> exported=Collections.synchronizedList(new ArrayList<>());
 public static volatile CountDownLatch entered,release;public static volatile boolean fail;public static volatile String thread;public static int audioCopies;
 public static void exportAudio(android.content.Context c,File f)throws IOException{export(c,f);audioCopies++;}
 public static void export(android.content.Context c,File f)throws IOException{
 thread=Thread.currentThread().getName();CountDownLatch a=entered,b=release;if(a!=null)a.countDown();
 try{if(b!=null&&!b.await(5,TimeUnit.SECONDS))throw new IOException("fixture wait");}catch(InterruptedException e){throw new IOException(e);}
 if(fail)throw new IOException("/private/fixture-secret-media.jpg");if(!f.isFile())throw new IOException("fixture missing");exported.add(f);}}''',
'com/whatsapp/infra/core/jid/Jid.java': '''package com.whatsapp.infra.core.jid;public abstract class Jid{public abstract String getRawString();}''',
'X/Chat.java': '''package X;public class Chat extends com.whatsapp.infra.core.jid.Jid{public final String value;
 public Chat(String v){value=v;}public String getRawString(){return value;}}''',
'X/Key.java': '''package X;public class Key{public final Chat chat;public final String id;public final boolean own;
 public Key(Chat c,String i,boolean o){chat=c;id=i;own=o;}}''',
'X/Message.java': 'package X;public class Message{public final Key key;public Message(Key k){key=k;}}',
'X/Media.java': '''package X;public class Media extends Message{public java.io.File unrelated;public Data data;public Data decoyData;
 public Media(Key k,Data d){super(k);data=d;}}''',
'X/Data.java': '''package X;import java.io.*;public class Data{public File thumbnail;private File cached;public final String path;
 public int calls;public Runnable during;public Error fatal;
 public Data(String p){path=p;}public File canonicalFile(){calls++;if(fatal!=null)throw fatal;if(during!=null)during.run();
 if(cached==null&&path!=null)cached=new File(path);return cached;}public File wrongFile(){return thumbnail;}}''',
'X/Page.java': 'package X;public class Page extends androidx.viewpager.widget.ViewPager{}',
'com/whatsapp/mediaview/ui/MediaViewBaseFragment.java': '''package com.whatsapp.mediaview.ui;public class MediaViewBaseFragment extends androidx.fragment.app.Fragment{
 public X.Page page=new X.Page();public X.Page decoyPage=new X.Page();}''',
'com/whatsapp/mediaview/MediaViewFragment.java': '''package com.whatsapp.mediaview;import android.view.*;import X.*;
 public class MediaViewFragment extends com.whatsapp.mediaview.ui.MediaViewBaseFragment{
 public Media[] messages;public int selectedCalls,initialCalls;public Runnable during;
 public static Media selected(MediaViewFragment v,int i){v.selectedCalls++;if(v.during!=null)v.during.run();return i>=0&&i<v.messages.length?v.messages[i]:null;}
 public static Media decoy(MediaViewFragment v,int i){return v.messages[0];}
 public Media initial(){initialCalls++;return messages[0];}
 public void create(MenuInflater i,Menu m){}public void prepare(Menu m){}public void unrelatedPrepare(Menu m){}
 public boolean onOptionsItemSelected(MenuItem i){return true;}}''',
'com/whatsapp/mediaview/menu/MediaViewMenu.java': '''package com.whatsapp.mediaview.menu;import android.view.*;import android.content.*;import X.*;
 public class MediaViewMenu{public void createHost(Context c,Menu m,androidx.fragment.app.Fragment f,Chat j,Message v,int t,boolean b){}
 public void clickHost(MenuItem i,androidx.fragment.app.Fragment f,Media m,int t){}}''',
'com/whatsapp/viewonce/ui/messaging/ViewOnceViewerActivity.java': '''package com.whatsapp.viewonce.ui.messaging;
 public class ViewOnceViewerActivity extends android.app.Activity{public boolean onCreateOptionsMenu(android.view.Menu m){return true;}}''',
}
DEX_STUBS = {
'org/luckypray/dexkit/query/enums/StringMatchType.java': 'package org.luckypray.dexkit.query.enums;public enum StringMatchType{Contains,EndsWith}',
'org/luckypray/dexkit/query/FindClass.java': 'package org.luckypray.dexkit.query;public class FindClass{public static FindClass create(){return new FindClass();}public FindClass matcher(Object m){return this;}}',
'org/luckypray/dexkit/query/FindMethod.java': 'package org.luckypray.dexkit.query;public class FindMethod{public static FindMethod create(){return new FindMethod();}public FindMethod matcher(Object m){return this;}}',
'org/luckypray/dexkit/query/matchers/ClassMatcher.java': 'package org.luckypray.dexkit.query.matchers;public class ClassMatcher{public static ClassMatcher create(){return new ClassMatcher();}public ClassMatcher className(String n,Object t){return this;}}',
'org/luckypray/dexkit/query/matchers/MethodMatcher.java': 'package org.luckypray.dexkit.query.matchers;public class MethodMatcher{public static MethodMatcher create(){return new MethodMatcher();}public MethodMatcher usingNumbers(int n){return this;}}',
'org/luckypray/dexkit/result/ClassData.java': 'package org.luckypray.dexkit.result;public class ClassData{public Class<?> getInstance(ClassLoader l){return com.whatsapp.viewonce.ui.messaging.ViewOnceViewerActivity.class;}}',
'org/luckypray/dexkit/result/ClassDataList.java': 'package org.luckypray.dexkit.result;public class ClassDataList{public ClassData firstOrNull(){return new ClassData();}}',
'org/luckypray/dexkit/result/FieldUsingType.java': 'package org.luckypray.dexkit.result;public enum FieldUsingType{Read,Write;public boolean isRead(){return this==Read;}}',
'org/luckypray/dexkit/result/FieldData.java': 'package org.luckypray.dexkit.result;public class FieldData{public final java.lang.reflect.Field field;public String ownerOverride;public boolean unavailable;public FieldData(java.lang.reflect.Field f){field=f;}public String getTypeName(){return field.getType().getName();}public String getDeclaredClassName(){return ownerOverride!=null?ownerOverride:field.getDeclaringClass().getName();}public java.lang.reflect.Field getFieldInstance(ClassLoader l){if(unavailable)throw new AssertionError("Unrelated optional field owner resolved");return field;}}',
'org/luckypray/dexkit/result/UsingFieldData.java': 'package org.luckypray.dexkit.result;public class UsingFieldData{public final FieldData field;public FieldUsingType type=FieldUsingType.Read;public UsingFieldData(java.lang.reflect.Field f){field=new FieldData(f);}public FieldData getField(){return field;}public FieldUsingType getUsingType(){return type;}}',
'org/luckypray/dexkit/result/MethodDataList.java': 'package org.luckypray.dexkit.result;public class MethodDataList extends java.util.ArrayList<MethodData>{}',
'org/luckypray/dexkit/result/MethodData.java': '''package org.luckypray.dexkit.result;import java.lang.reflect.*;import java.util.*;public class MethodData{
 public final Method method;public boolean callable=true,unavailable;public String ownerOverride,returnOverride;public final MethodDataList calls=new MethodDataList();public final List<UsingFieldData> fields=new ArrayList<>();public final List<String> strings=new ArrayList<>();
 public MethodData(Method m){method=m;}public boolean isMethod(){return callable;}public Method getMethodInstance(ClassLoader l){if(!callable||unavailable)throw new AssertionError("Unrelated class or constructor resolved as Method");return method;}
 public String getDeclaredClassName(){return ownerOverride!=null?ownerOverride:method.getDeclaringClass().getName();}public String getReturnTypeName(){return returnOverride!=null?returnOverride:method.getReturnType().getName();}
 public String getName(){return method.getName();}public List<String> getUsingStrings(){return strings;}
 public MethodDataList getInvokes(){return calls;}public List<UsingFieldData> getUsingFields(){return fields;}
 public int getParamCount(){return method.getParameterCount();}public List<String> getParamTypeNames(){List<String> a=new ArrayList<>();for(Class<?> c:method.getParameterTypes())a.add(c.getName());return a;}}''',
'org/luckypray/dexkit/DexKitBridge.java': '''package org.luckypray.dexkit;import java.lang.reflect.*;import java.util.*;import org.luckypray.dexkit.result.*;
 public class DexKitBridge{public final Map<Method,MethodData> entries=new HashMap<>();public Method fallback;
 public MethodData getMethodData(Method m){return entries.get(m);}public ClassDataList findClass(org.luckypray.dexkit.query.FindClass c){return new ClassDataList();}
 public MethodDataList findMethod(org.luckypray.dexkit.query.FindMethod q){MethodDataList result=new MethodDataList();if(fallback!=null)result.add(new MethodData(fallback));return result;}}''',
}

def write(d, mapping):
    for relative, text in mapping.items():
        p=d/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline-hook',type=Path)
    p.add_argument('--scenario',default='all');p.add_argument('--dexkit-jar',type=Path);p.add_argument('--audio',action='store_true')
    a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='waex-view-once-') as temporary:
        d=Path(temporary);write(d,STUBS)
        hook=a.baseline_hook or SOURCE/'DownloadViewOnceHook.java'
        helpers=[SOURCE/'ViewOnceMediaResolver.java']
        if (SOURCE/'ViewOnceAudioResolver.java').exists():helpers.append(SOURCE/'ViewOnceAudioResolver.java')
        production=[str(hook),*map(str,helpers)]
        # A baseline source may have a different artifact basename, so compile its exact bytes
        # under Java's required public-class name without changing its contents.
        staged=d/'DownloadViewOnceHook.java';staged.write_bytes(hook.read_bytes());production[0]=str(staged)
        if a.dexkit_jar:
            dependencies=[str(f) for f in d.rglob('*.java') if f != staged]
            subprocess.run(['javac','--release','17','-cp',str(a.dexkit_jar),'-d',str(d/'real-api'),
                            *production,*dependencies],check=True,timeout=60)
            print('REAL_DEXKIT_API_COMPILE_OK: complete hook and resolver; no DexKit doubles',flush=True)
        write(d,DEX_STUBS)
        fixture=ROOT/'qa/view_once/ViewOnceDownloadTest.java'
        fixtures=[str(fixture)]
        if a.audio:
            from view_once_audio_fixtures import AUDIO_STUBS
            write(d,AUDIO_STUBS)
            fixtures.append(str(ROOT/'qa/view_once/ViewOnceAudioTest.java'))
        sources=list(map(str,d.rglob('*.java')))
        # staged hook is already in the source list.
        subprocess.run(['javac','--release','17','-d',str(d/'classes'),*map(str,helpers),
                        *fixtures,*sources],check=True,timeout=60)
        print('COMPILE_OK: complete hook, complete resolver and explicit host/Android doubles',flush=True)
        subprocess.run(['java','-Xshare:off','-cp',str(d/'classes'),
                        'com.waenhancer.xposed.features.media.'+('ViewOnceAudioTest' if a.audio else 'ViewOnceDownloadTest'),
                        a.scenario,*(['baseline'] if a.baseline_hook else [])],check=True,timeout=60)
        print('SOURCE_SHA256:',hook.name,hashlib.sha256(hook.read_bytes()).hexdigest(),flush=True)

if __name__=='__main__':main()
