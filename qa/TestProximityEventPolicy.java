package com.waenhancer.xposed.features.media;

public final class TestProximityEventPolicy {
    private static int checks;
    private static void check(boolean ok, String label) {
        checks++;
        if (!ok) throw new AssertionError(label);
    }
    public static void main(String[] args) {
        float[] accelerometer = {0f, 2f, 3f};
        check(!ProximityEventPolicy.replaceNearWithFar(1, 20f, accelerometer), "accelerometer not proximity");
        check(accelerometer[0] == 0f, "do not alter unrelated sensors");
        float[] gyro = {1f};
        check(!ProximityEventPolicy.replaceNearWithFar(4, 99f, gyro), "gyroscope not proximity");
        check(gyro[0] == 1f, "gyro stays unchanged");
        float[] near = {0f, 99f};
        check(ProximityEventPolicy.replaceNearWithFar(8, 5f, near), "proximity event accepted");
        check(near[0] == 5f, "far value uses measured sensor maximum range");
        check(near[1] == 99f, "other coordinates preserved");
        check(!ProximityEventPolicy.replaceNearWithFar(8, 0f, near), "zero max range rejected");
        check(!ProximityEventPolicy.replaceNearWithFar(8, -1f, near), "negative max range rejected");
        check(!ProximityEventPolicy.replaceNearWithFar(8, Float.NaN, near), "NaN max range rejected");
        check(!ProximityEventPolicy.replaceNearWithFar(8, Float.POSITIVE_INFINITY, near), "infinite max range rejected");
        check(!ProximityEventPolicy.replaceNearWithFar(8, 5f, null), "null array rejected");
        check(!ProximityEventPolicy.replaceNearWithFar(8, 5f, new float[0]), "empty array rejected");
        check(near[0] == 5f, "invalid events do not mutate state");
        System.out.println("PASS: " + checks + " proximity sensor type, range and other-sensor isolation tests");
    }
}
