package com.waenhancer.xposed.features.media;

import android.content.Context;
import android.content.SharedPreferences;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.util.SparseArray;
import java.util.concurrent.atomic.AtomicBoolean;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

/**
 * Proximity Sensor Hook:
 * Prevents screen turning off when playing audio / voice notes by suppressing proximity sensor events.
 */
public class ProximitySensorHook extends BaseFeature {

    private static final String TAG = "[WAEX][ProximitySensor]";
    private static final String PREF_KEY = "disable_sensor_proximity";
    private static final AtomicBoolean SENSOR_MAP_WARNING = new AtomicBoolean(false);

    public ProximitySensorHook(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public void hook() throws Throwable {
        hookProximitySensor();
    }

    private void hookProximitySensor() {
        try {
            Class<?> sensorQueue = XposedHelpers.findClassIfExists(
                    "android.hardware.SystemSensorManager$SensorEventQueue", classLoader);
            if (sensorQueue == null) return;
            XposedBridge.hookAllMethods(sensorQueue, "dispatchSensorEvent", new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    if (!isProximitySensorDisabled() || param.args == null || param.args.length < 2
                            || !(param.args[0] instanceof Integer)
                            || !(param.args[1] instanceof float[])) return;
                    try {
                        // A queue carries many sensor types. Never alter accelerometer/gyro events.
                        // AOSP keeps its handle -> SensorEvent mapping in mSensorsEvents.
                        Object mapping = XposedHelpers.getObjectField(param.thisObject, "mSensorsEvents");
                        if (!(mapping instanceof SparseArray<?>)) return;
                        Object candidate = ((SparseArray<?>) mapping).get((Integer) param.args[0]);
                        if (!(candidate instanceof SensorEvent)) return;
                        Sensor sensor = ((SensorEvent) candidate).sensor;
                        if (sensor == null) return;
                        ProximityEventPolicy.replaceNearWithFar(
                                sensor.getType(), sensor.getMaximumRange(), (float[]) param.args[1]);
                    } catch (Throwable failure) {
                        // Vendor sensor queue layouts may differ: fail closed, not all-sensor mutation.
                        if (SENSOR_MAP_WARNING.compareAndSet(false, true)) {
                            XposedBridge.log(TAG + " Sensor-event mapping unavailable: "
                                    + failure.getClass().getSimpleName());
                        }
                    }
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking Proximity Sensor: " + t.getClass().getSimpleName());
        }
    }

    private boolean isProximitySensorDisabled() {
        return isEnabled(PREF_KEY, false) || isEnabled("proximity_audios", false);
    }

    @NonNull
    @Override
    public String getName() {
        return "Disable Proximity Sensor";
    }
}
