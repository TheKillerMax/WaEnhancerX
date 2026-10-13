package com.waenhancer.xposed.features.media;

/** Android-independent policy for the one sensor we are allowed to override. */
final class ProximityEventPolicy {
    // android.hardware.Sensor.TYPE_PROXIMITY, stable across Android API levels.
    private static final int PROXIMITY_TYPE = 8;

    private ProximityEventPolicy() {}

    static boolean replaceNearWithFar(int sensorType, float maximumRange, float[] values) {
        if (sensorType != PROXIMITY_TYPE || values == null || values.length == 0
                || !Float.isFinite(maximumRange) || maximumRange <= 0f) return false;
        values[0] = maximumRange;
        return true;
    }
}
