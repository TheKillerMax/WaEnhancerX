#!/usr/bin/env python3
"""Compile and exercise real proximity hook/policy with minimal Android/Xposed stubs.

Not LSPosed device validation; Android builds may differ in internal field names.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "app/src/main/java/com/waenhancer/xposed/features/media"
HOOK = (PATH / "ProximitySensorHook.java").read_text(encoding="utf-8")
assert 'Sensor.TYPE_PROXIMITY' in HOOK
assert 'getObjectField(queue, "mManager")' in HOOK
assert 'getObjectField(manager, "mHandleToSensor")' in HOOK
assert 'new XC_MethodHook()' in HOOK
assert 'ProximityDispatchPolicy.replaceNearWithFar(' in HOOK
assert 'values[0] = 100.0f' not in HOOK
assert 'SystemSensorManager$SensorEventQueue' in HOOK
STUBS = {
    "android/content/Context.java": "package android.content; public class Context {}",
    "android/content/SharedPreferences.java": "package android.content; public interface SharedPreferences {boolean getBoolean(String key, boolean fallback);}",
    "androidx/annotation/NonNull.java": "package androidx.annotation; public @interface NonNull {}",
    "android/hardware/Sensor.java": '''package android.hardware;
public class Sensor {
 public static final int TYPE_PROXIMITY = 8;
 private final int type; private final float maximum;
 public Sensor(int type,float maximum){this.type=type;this.maximum=maximum;}
 public int getType(){return type;}
 public float getMaximumRange(){return maximum;}
}''',
    "android/util/SparseArray.java": '''package android.util;
import java.util.HashMap;
public class SparseArray<T> {
 private final HashMap<Integer,T> m = new HashMap<>();
 public T get(int i){return m.get(i);}
 public void put(int i,T v){m.put(i,v);}
}''',
    "android/hardware/SystemSensorManager.java": '''package android.hardware;
import java.util.HashMap;
public final class SystemSensorManager {
 private final HashMap<Integer,Sensor> mHandleToSensor = new HashMap<>();
 public void register(int handle,Sensor sensor){mHandleToSensor.put(handle,sensor);}
 public static final class SensorEventQueue {
  private final SystemSensorManager mManager;
  public SensorEventQueue(SystemSensorManager manager){mManager=manager;}
  public void dispatchSensorEvent(int handle,float[] v,int accuracy,long stamp){}
 }
}''',
    "com/waenhancer/xposed/core/BaseFeature.java": '''package com.waenhancer.xposed.core;
import android.content.Context; import android.content.SharedPreferences;
public abstract class BaseFeature {
 protected final Context context; protected final ClassLoader classLoader; protected final SharedPreferences prefs;
 public BaseFeature(Context c,ClassLoader l,SharedPreferences p){context=c;classLoader=l;prefs=p;}
 protected boolean isEnabled(String key,boolean fallback){return prefs.getBoolean(key,fallback);}
 public abstract void hook() throws Throwable;
 public abstract String getName();
}''',
    "de/robv/android/xposed/XC_MethodHook.java": '''package de.robv.android.xposed;
public abstract class XC_MethodHook {
 public static class MethodHookParam {public Object thisObject; public Object[] args;}
 protected void beforeHookedMethod(MethodHookParam p) throws Throwable {}
 public final void dispatchForTest(MethodHookParam p) throws Throwable { beforeHookedMethod(p); }
}''',
    "de/robv/android/xposed/XposedBridge.java": '''package de.robv.android.xposed;
public final class XposedBridge {
 public static XC_MethodHook captured;
 public static void hookAllMethods(Class<?> cls,String name,XC_MethodHook hook){captured=hook;}
 public static void log(String message){}
}''',
    "de/robv/android/xposed/XposedHelpers.java": '''package de.robv.android.xposed;
import java.lang.reflect.Field;
public final class XposedHelpers {
 public static Class<?> findClassIfExists(String name,ClassLoader loader){
  try{return Class.forName(name,false,loader);}catch(ClassNotFoundException e){return null;}
 }
 public static Object getObjectField(Object obj,String name){
  Class<?> cls=obj.getClass();
  while(cls!=null){
   try{Field f=cls.getDeclaredField(name);f.setAccessible(true);return f.get(obj);}
   catch(NoSuchFieldException e){cls=cls.getSuperclass();}
   catch(IllegalAccessException e){throw new IllegalStateException(e);}
  }
  throw new IllegalStateException("No field: "+name);
 }
}''',
    "com/waenhancer/xposed/features/media/TestProximityHookIntegration.java": '''package com.waenhancer.xposed.features.media;
import android.content.Context;
import android.content.SharedPreferences;
import android.hardware.Sensor;
import android.hardware.SystemSensorManager;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
public final class TestProximityHookIntegration {
 static int count;
 static void test(boolean ok,String message){count++;if(!ok)throw new AssertionError(message);}
 static final class Prefs implements SharedPreferences {
  boolean enabled;
  public boolean getBoolean(String key,boolean fallback) {
   return key.equals("disable_sensor_proximity") ? enabled : false;
  }
 }
 static void send(Object queue,int handle,float[] values) throws Throwable {
  XC_MethodHook.MethodHookParam p=new XC_MethodHook.MethodHookParam();
  p.thisObject=queue;p.args=new Object[]{handle, values, 0, 0L};
  XposedBridge.captured.dispatchForTest(p);
 }
 public static void main(String[] args) throws Throwable {
  Prefs prefs=new Prefs();
  ProximitySensorHook hook=new ProximitySensorHook(new Context(),
      TestProximityHookIntegration.class.getClassLoader(),prefs);
  hook.hook();
  test(XposedBridge.captured!=null,"hook installed");
  SystemSensorManager manager=new SystemSensorManager();
  manager.register(21,new Sensor(Sensor.TYPE_PROXIMITY,6f));
  manager.register(22,new Sensor(1,10f));
  manager.register(23,new Sensor(4,12f));
  SystemSensorManager.SensorEventQueue queue=new SystemSensorManager.SensorEventQueue(manager);
  float[] near={0f,77f};
  send(queue,21,near);
  test(near[0]==0f,"disabled setting leaves proximity sensor unchanged");
  prefs.enabled=true;
  float[] accelerometer={1.2f,2f,3f};send(queue,22,accelerometer);
  test(accelerometer[0]==1.2f && accelerometer[1]==2f,"accelerometer unchanged");
  float[] gyro={0.2f,4f};send(queue,23,gyro);
  test(gyro[0]==0.2f,"gyroscope unchanged");
  send(queue,21,near);
  test(near[0]==6f && near[1]==77f,"actual proximity sensor far reading applied");
  float[] unknown={0.4f};send(queue,99,unknown);
  test(unknown[0]==0.4f,"unknown handle unchanged");
  float[] blank={};send(queue,21,blank);
  test(blank.length==0,"empty sensor value safe");
  System.out.println("PASS: "+count+" simulated sensor-dispatch assertions");
 }
}''',
}
with tempfile.TemporaryDirectory(prefix="waex_proximity_qa_") as dest:
    root=Path(dest)
    sources=[]
    for name,code in STUBS.items():
        path=root / name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(code,encoding="utf-8")
        sources.append(str(path))
    sources += [str(PATH/'ProximitySensorHook.java'),str(PATH/'ProximityDispatchPolicy.java'),
                str(ROOT/'qa/java/TestProximityDispatchPolicy.java')]
    subprocess.run(["javac","--release","17","-d",dest,*sources],check=True)
    for name in ("TestProximityHookIntegration","TestProximityDispatchPolicy"):
        subprocess.run(["java","-cp",dest,
                        "com.waenhancer.xposed.features.media."+name],check=True)
print("PASS: production proximity hook and policy compiled against simulated Android dispatch")
