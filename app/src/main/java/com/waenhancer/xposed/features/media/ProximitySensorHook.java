package com.waenhancer.xposed.features.media;

import android.content.Context;
import android.content.SharedPreferences;
import android.hardware.Sensor;
import android.util.SparseArray;
import java.util.Map;
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

    public ProximitySensorHook(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public void hook() throws Throwable {
        hookProximitySensor();
    }

    private void hookProximitySensor() {
        try {
            Class<?> eventQueue = XposedHelpers.findClassIfExists(
                    "android.hardware.SystemSensorManager$SensorEventQueue", classLoader);
            if (eventQueue == null) {
                XposedBridge.log(TAG + " SensorEventQueue unavailable; events left untouched");
                return;
            }
            XposedBridge.hookAllMethods(eventQueue, "dispatchSensorEvent", new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    if (!isProximitySensorDisabled() || param.args == null || param.args.length < 2
                            || !(param.args[0] instanceof Integer) || !(param.args[1] instanceof float[])) {
                        return;
                    }
                    Sensor sensor = lookupSensor(param.thisObject, (Integer) param.args[0]);
                    if (sensor == null) return; // Fail closed: never alter an unidentified sensor.
                    ProximityDispatchPolicy.replaceNearWithFar(
                            sensor.getType() == Sensor.TYPE_PROXIMITY,
                            sensor.getMaximumRange(), (float[]) param.args[1]);
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking Proximity Sensor: " + t.getClass().getSimpleName());
        }
    }

    /** Resolve the dispatched handle using the same table as Android's sensor queue. */
    private static Sensor lookupSensor(Object queue, int handle) {
        if (queue == null) return null;
        try {
            Object manager = XposedHelpers.getObjectField(queue, "mManager");
            if (manager == null) return null;
            Object handles = XposedHelpers.getObjectField(manager, "mHandleToSensor");
            Object sensor = null;
            if (handles instanceof Map<?, ?>) {
                sensor = ((Map<?, ?>) handles).get(handle);
            } else if (handles instanceof SparseArray<?>) {
                sensor = ((SparseArray<?>) handles).get(handle);
            }
            return sensor instanceof Sensor ? (Sensor) sensor : null;
        } catch (Throwable ignored) {
            return null;
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
