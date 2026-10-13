package com.waenhancer.xposed.features.media;

/** Small, Android-free guard for sensor values modified by the proximity hook. */
final class ProximityDispatchPolicy {
    private ProximityDispatchPolicy() {}

    static boolean replaceNearWithFar(boolean confirmedProximity, float maximumRange, float[] values) {
        if (!confirmedProximity || values == null || values.length == 0 ||
                !(maximumRange > 0f) || Float.isNaN(maximumRange) || Float.isInfinite(maximumRange)) {
            return false;
        }
        // Android's far distance is reported at the proximity sensor's maximum range.
        values[0] = maximumRange;
        return true;
    }
}
