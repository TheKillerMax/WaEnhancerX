"""Explicit API doubles for IG status control-flow tests, not an Android renderer."""

STUBS = {
    'android/content/Context.java': '''package android.content;
import java.io.File; import android.content.res.Resources;
public class Context {
 public Context application=this; public File root=new File(System.getProperty("qa.root"));
 public final Resources resources=new Resources();
 public Context getApplicationContext(){return application;}
 public Resources getResources(){return resources;}
 public File getDatabasePath(String name){com.waenhancer.utils.ContactNameResolver.io();return new File(root,name);}
 public File getFilesDir(){com.waenhancer.utils.ContactNameResolver.io();return root;}
 public File getCacheDir(){com.waenhancer.utils.ContactNameResolver.io();return root;}
 public ClassLoader getClassLoader(){return getClass().getClassLoader();}
}''',
    'android/content/res/Resources.java': '''package android.content.res;
public class Resources { public final Configuration config=new Configuration();
 public final android.util.DisplayMetrics metrics=new android.util.DisplayMetrics();
 public Configuration getConfiguration(){return config;} public android.util.DisplayMetrics getDisplayMetrics(){return metrics;}}
''',
    'android/content/res/Configuration.java': '''package android.content.res;
public class Configuration {public static final int UI_MODE_NIGHT_MASK=48,UI_MODE_NIGHT_YES=32;public int uiMode;}''',
    'android/util/DisplayMetrics.java': '''package android.util;public class DisplayMetrics {public float density=1;}''',
    'android/util/TypedValue.java': '''package android.util;public class TypedValue {public static final int COMPLEX_UNIT_SP=2;}''',
    'android/app/Activity.java': '''package android.app;public class Activity extends android.content.Context {public void startActivity(android.content.Intent i){}}''',
    'android/content/Intent.java': '''package android.content;public class Intent {public Intent(Context c,Class<?> t){}public Intent putExtra(String k,String v){return this;}public Intent putExtra(String k,int v){return this;}}''',
    'android/os/Looper.java': '''package android.os;public class Looper {private static final Looper MAIN=new Looper();public static Looper getMainLooper(){return MAIN;}}''',
    'android/os/Handler.java': '''package android.os;
import java.util.concurrent.*;
public class Handler {
 public static final LinkedBlockingQueue<Runnable> queue=new LinkedBlockingQueue<>();public static boolean accept=true;
 public Handler(Looper l){} public boolean post(Runnable r){if(accept)queue.add(r);return accept;}
 public void removeCallbacks(Runnable r){queue.remove(r);}
 public static void next()throws Exception{Runnable r=queue.poll(5,TimeUnit.SECONDS);if(r==null)throw new AssertionError("UI callback timed out");r.run();}
 public static void drain(){Runnable r;while((r=queue.poll())!=null)r.run();}
}''',
    'android/view/View.java': '''package android.view;
import android.content.Context;import android.os.*;import java.util.*;
public class View {
 public static final int GONE=8,VISIBLE=0,TEXT_ALIGNMENT_CENTER=4;
 public interface OnClickListener {void onClick(View v);}
 public interface OnAttachStateChangeListener {void onViewAttachedToWindow(View v);void onViewDetachedFromWindow(View v);}
 final Context context;Object tag;ViewGroup.LayoutParams params;public int visibility=VISIBLE;public OnClickListener click;
 final List<OnAttachStateChangeListener> listeners=new ArrayList<>();
 public View(Context c){context=c;}public Context getContext(){return context;}
 public void setTag(Object o){tag=o;}public Object getTag(){return tag;}
 public void setOnClickListener(OnClickListener c){click=c;}public void setPadding(int a,int b,int c,int d){}
 public void setLayoutParams(ViewGroup.LayoutParams p){params=p;}public ViewGroup.LayoutParams getLayoutParams(){return params;}
 public void setBackground(android.graphics.drawable.Drawable d){} public void setVisibility(int v){visibility=v;}
 public void setTextAlignment(int a){}public int getHeight(){return 80;}public void setTranslationY(float f){}
 public void addOnAttachStateChangeListener(OnAttachStateChangeListener l){listeners.add(l);}
 public void attach(){onAttachedToWindow();for(OnAttachStateChangeListener l:listeners)l.onViewAttachedToWindow(this);}
 public void detach(){for(OnAttachStateChangeListener l:listeners)l.onViewDetachedFromWindow(this);onDetachedFromWindow();}
 protected void onAttachedToWindow(){}protected void onDetachedFromWindow(){}
 public boolean post(Runnable r){return new Handler(Looper.getMainLooper()).post(r);}
 public boolean removeCallbacks(Runnable r){return Handler.queue.remove(r);}public void invalidate(){}
}''',
    'android/view/ViewGroup.java': '''package android.view;import android.content.Context;import java.util.*;
public class ViewGroup extends View {public final List<View> children=new ArrayList<>();public ViewGroup(Context c){super(c);}
 public static class LayoutParams{public static final int MATCH_PARENT=-1,WRAP_CONTENT=-2;public int width,height;public LayoutParams(int w,int h){width=w;height=h;}}
 public void addView(View v){children.add(v);}
}''',
    'android/view/Gravity.java': '''package android.view;public class Gravity{public static final int CENTER_HORIZONTAL=1,CENTER=17;}''',
    'android/widget/ListAdapter.java': '''package android.widget;public interface ListAdapter {}''',
    'android/widget/BaseAdapter.java': '''package android.widget;public class BaseAdapter implements ListAdapter {public int notifications;public Runnable onNotify;public void notifyDataSetChanged(){notifications++;if(onNotify!=null)onNotify.run();}}''',
    'android/widget/ArrayAdapter.java': '''package android.widget;import android.content.Context;import android.view.*;
public class ArrayAdapter<T> extends BaseAdapter {private final Context context;public ArrayAdapter(Context c,int id){context=c;}public Context getContext(){return context;}
 public int getCount(){return 0;}public View getView(int p,View c,ViewGroup g){return null;}}''',
    'android/widget/FrameLayout.java': '''package android.widget;public class FrameLayout extends android.view.ViewGroup {public FrameLayout(android.content.Context c){super(c);}public static class LayoutParams extends android.view.ViewGroup.LayoutParams{public LayoutParams(int w,int h){super(w,h);}}}''',
    'android/widget/LinearLayout.java': '''package android.widget;public class LinearLayout extends android.view.ViewGroup {public static final int VERTICAL=1;public LinearLayout(android.content.Context c){super(c);}public void setOrientation(int o){}public void setGravity(int g){}public static class LayoutParams extends android.view.ViewGroup.LayoutParams{public int topMargin;public LayoutParams(int w,int h){super(w,h);}}}''',
    'android/widget/RelativeLayout.java': '''package android.widget;public class RelativeLayout extends android.view.ViewGroup {public static final int ALIGN_PARENT_BOTTOM=1,ALIGN_PARENT_END=2,CENTER_IN_PARENT=3;public RelativeLayout(android.content.Context c){super(c);}public static class LayoutParams extends android.view.ViewGroup.LayoutParams{public LayoutParams(int w,int h){super(w,h);}public void addRule(int r){}}}''',
    'android/widget/ImageView.java': '''package android.widget;public class ImageView extends android.view.View {public enum ScaleType{CENTER_CROP}public android.graphics.drawable.Drawable image;public ImageView(android.content.Context c){super(c);}public void setScaleType(ScaleType t){}public void setImageDrawable(android.graphics.drawable.Drawable d){image=d;}}''',
    'android/widget/TextView.java': '''package android.widget;public class TextView extends android.view.View {public CharSequence text;public TextView(android.content.Context c){super(c);}public void setText(CharSequence t){text=t;}public void setEllipsize(android.text.TextUtils.TruncateAt t){}public void setGravity(int g){}public void setTextSize(int u,float s){}public void setTypeface(android.graphics.Typeface t){}public void setMaxLines(int n){}public void setTextColor(int c){}}''',
    'android/widget/Toast.java': '''package android.widget;public class Toast{public static final int LENGTH_SHORT=0;public static Toast makeText(android.content.Context c,CharSequence t,int d){return new Toast();}public void show(){}}''',
    'android/graphics/Bitmap.java': '''package android.graphics;
public class Bitmap {public enum Config{ARGB_8888}final int w,h;public Bitmap(int width,int height){w=width;h=height;}public int getWidth(){return w;}public int getHeight(){return h;}public static Bitmap createBitmap(int w,int h,Config c){if(w<1||h<1)throw new IllegalArgumentException();return new Bitmap(w,h);}}''',
    'android/graphics/BitmapFactory.java': '''package android.graphics;
import java.util.*;public class BitmapFactory {
 public static final List<String> calls=Collections.synchronizedList(new ArrayList<>());
 public static int width=4000,height=3000;public static class Options{public boolean inJustDecodeBounds;public int outWidth,outHeight,inSampleSize=1;}
 public static Bitmap decodeFile(String path){com.waenhancer.utils.ContactNameResolver.io();calls.add("full:file");return new Bitmap(width,height);}
 public static Bitmap decodeByteArray(byte[] b,int s,int n){com.waenhancer.utils.ContactNameResolver.io();calls.add("full:blob");return new Bitmap(width,height);}
 public static Bitmap decodeFile(String path,Options o){return decode(o,"file");}
 public static Bitmap decodeByteArray(byte[] b,int s,int n,Options o){return decode(o,"blob");}
 static Bitmap decode(Options o,String kind){com.waenhancer.utils.ContactNameResolver.io();if(o.inJustDecodeBounds){calls.add("bounds:"+kind);o.outWidth=width;o.outHeight=height;return null;}calls.add("sample:"+kind+":"+o.inSampleSize);return new Bitmap((width+o.inSampleSize-1)/o.inSampleSize,(height+o.inSampleSize-1)/o.inSampleSize);}
}''',
    'android/graphics/Canvas.java': '''package android.graphics;public class Canvas{public static Paint lastCirclePaint;public Canvas(Bitmap b){}public void drawCircle(float x,float y,float r,Paint p){lastCirclePaint=p;}public void drawText(String s,float x,float y,Paint p){}public void drawLine(float a,float b,float c,float d,Paint p){}public void drawRoundRect(RectF r,float a,float b,Paint p){}}''',
    'android/graphics/Paint.java': '''package android.graphics;public class Paint{public static final int ANTI_ALIAS_FLAG=1,FILTER_BITMAP_FLAG=2;public Shader shader;public int flags;public enum Align{CENTER}public enum Cap{ROUND}public static class FontMetrics{public float ascent,descent;}public Paint(int f){flags=f;}public void setShader(Shader s){shader=s;}public void setColor(int c){}public void setStrokeWidth(float f){}public void setStrokeCap(Cap c){}public void setTextSize(float s){}public void setTypeface(Typeface t){}public void setTextAlign(Align a){}public FontMetrics getFontMetrics(){return new FontMetrics();}}''',
    'android/graphics/Shader.java': '''package android.graphics;public class Shader{public enum TileMode{CLAMP}}''',
    'android/graphics/BitmapShader.java': '''package android.graphics;public class BitmapShader extends Shader{public final Bitmap source;public Matrix matrix;public BitmapShader(Bitmap b,TileMode a,TileMode c){source=b;}public void setLocalMatrix(Matrix m){matrix=m;}}''',
    'android/graphics/Matrix.java': '''package android.graphics;public class Matrix{public float sx,sy,tx,ty;public void setScale(float x,float y){sx=x;sy=y;}public boolean postTranslate(float x,float y){tx=x;ty=y;return true;}}''',
    'android/graphics/RectF.java': '''package android.graphics;public class RectF{public RectF(float a,float b,float c,float d){}}''',
    'android/graphics/Color.java': '''package android.graphics;public class Color{public static final int WHITE=-1;}''',
    'android/graphics/Typeface.java': '''package android.graphics;public class Typeface{public static final Typeface DEFAULT=new Typeface(),DEFAULT_BOLD=new Typeface();public static final int BOLD=1;public static Typeface create(Typeface t,int s){return t;}}''',
    'android/graphics/drawable/Drawable.java': '''package android.graphics.drawable;public class Drawable{public int width=4096,height=4096;public void setBounds(int a,int b,int c,int d){width=c-a;height=d-b;}public void draw(android.graphics.Canvas c){}public int getIntrinsicWidth(){return width;}public int getIntrinsicHeight(){return height;}}''',
    'android/graphics/drawable/BitmapDrawable.java': '''package android.graphics.drawable;public class BitmapDrawable extends Drawable{final android.graphics.Bitmap bitmap;public BitmapDrawable(android.content.res.Resources r,android.graphics.Bitmap b){bitmap=b;}public android.graphics.Bitmap getBitmap(){return bitmap;}}''',
    'android/graphics/drawable/GradientDrawable.java': '''package android.graphics.drawable;public class GradientDrawable extends Drawable{public static final int OVAL=1;public void setShape(int s){}public void setColor(int c){}}''',
    'android/text/TextPaint.java': '''package android.text;public class TextPaint extends android.graphics.Paint{public TextPaint(int f){super(f);}}''',
    'android/text/TextUtils.java': '''package android.text;public class TextUtils{public enum TruncateAt{END}}''',
    'android/database/Cursor.java': '''package android.database;public class Cursor implements AutoCloseable{public boolean moveToFirst(){return false;}public int getInt(int c){return 0;}public long getLong(int c){return 0;}public String getString(int c){return null;}public byte[] getBlob(int c){return null;}public void close(){}}''',
    'android/database/sqlite/SQLiteDatabase.java': '''package android.database.sqlite;public class SQLiteDatabase{public static final int OPEN_READONLY=1;public static SQLiteDatabase openDatabase(String p,Object f,int flags){com.waenhancer.utils.ContactNameResolver.io();return new SQLiteDatabase();}public android.database.Cursor rawQuery(String q,String[] a){com.waenhancer.utils.ContactNameResolver.io();return new android.database.Cursor();}public void close(){}}''',
    'androidx/annotation/NonNull.java': '''package androidx.annotation;public @interface NonNull{}''',
    'androidx/annotation/Nullable.java': '''package androidx.annotation;public @interface Nullable{}''',
    'androidx/core/content/ContextCompat.java': '''package androidx.core.content;public class ContextCompat{}''',
    'com/waenhancer/xposed/core/components/WaexBottomSheet.java': '''package com.waenhancer.xposed.core.components;public class WaexBottomSheet{}''',
    'com/waenhancer/utils/UiText.java': '''package com.waenhancer.utils;public class UiText{public static String get(int id,String fallback){return fallback;}}''',
    'com/waenhancer/xposed/features/homescreen/MenuIconLoader.java': '''package com.waenhancer.xposed.features.homescreen;public class MenuIconLoader{public static android.graphics.drawable.Drawable load(android.content.Context c,String n){return null;}}''',
    'com/waenhancer/xposed/utils/ActivityTracker.java': '''package com.waenhancer.xposed.utils;public class ActivityTracker{public static android.app.Activity getCurrentActivity(){return null;}}''',
    'de/robv/android/xposed/XposedBridge.java': '''package de.robv.android.xposed;public class XposedBridge{public static void log(String s){}}''',
    'de/robv/android/xposed/XposedHelpers.java': '''package de.robv.android.xposed;public class XposedHelpers{public static Class<?> findClassIfExists(String n,ClassLoader l){return null;}}''',
    'com/whatsapp/jid/UserJid.java': '''package com.whatsapp.jid;public class UserJid{final String value;public UserJid(String v){value=v;}public String getRawString(){return value;}public String toString(){return value;}}''',
    'com/waenhancer/utils/ContactNameResolver.java': '''package com.waenhancer.utils;
import java.util.concurrent.*;import java.util.concurrent.atomic.*;
public class ContactNameResolver {
 public static final ContactNameResolver INSTANCE=new ContactNameResolver();
 public static Thread ui;public static final AtomicInteger mainIo=new AtomicInteger();
 public static final LinkedBlockingQueue<String> starts=new LinkedBlockingQueue<>();
 public static final ConcurrentHashMap<String,CountDownLatch> barriers=new ConcurrentHashMap<>();
 public static volatile android.content.Context lastContext;
 public static void io(){if(Thread.currentThread()==ui)mainIo.incrementAndGet();}
 public String resolveName(android.content.Context c,String jid,Object a,Object b){
  io();lastContext=c;starts.add(jid);CountDownLatch barrier=barriers.get(jid);
  if(barrier!=null)try{if(!barrier.await(5,TimeUnit.SECONDS))throw new AssertionError("name barrier timed out");}catch(InterruptedException e){Thread.currentThread().interrupt();}
  return "Name:"+jid;
 }
}''',
    'com/waenhancer/xposed/views/HorizontalListView.java': '''package com.waenhancer.xposed.views;public class HorizontalListView extends android.view.ViewGroup{public HorizontalListView(android.content.Context c){super(c);}public void setAdapter(android.widget.ListAdapter a){}}''',
}
