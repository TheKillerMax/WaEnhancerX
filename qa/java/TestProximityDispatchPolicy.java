package com.waenhancer.xposed.features.media;

public final class TestProximityDispatchPolicy {
    private static int checked;
    private static void assertTrue(boolean condition, String message) {
        checked++;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        float[] acc = {0.3f, 0.9f, 1.2f};
        assertTrue(!ProximityDispatchPolicy.replaceNearWithFar(false, 5f, acc), "other sensor untouched");
        assertTrue(acc[0] == 0.3f && acc[1] == 0.9f, "acceleration retained");
        float[] close = {0f, 7f};
        assertTrue(ProximityDispatchPolicy.replaceNearWithFar(true, 5f, close), "proximity far substitution");
        assertTrue(close[0] == 5f && close[1] == 7f, "only proximity distance modified");
        float[] alreadyFar = {5f};
        assertTrue(ProximityDispatchPolicy.replaceNearWithFar(true, 5f, alreadyFar), "idempotent far event");
        assertTrue(alreadyFar[0] == 5f, "far reading remains far");
        assertTrue(!ProximityDispatchPolicy.replaceNearWithFar(true, 5f, null), "null values rejected");
        assertTrue(!ProximityDispatchPolicy.replaceNearWithFar(true, 5f, new float[0]), "empty values rejected");
        for (float wrong : new float[]{0f, -1f, Float.NaN, Float.POSITIVE_INFINITY,
                Float.NEGATIVE_INFINITY}) {
            float[] sample = {0f};
            assertTrue(!ProximityDispatchPolicy.replaceNearWithFar(true, wrong, sample),
                    "invalid maximum range rejected");
            assertTrue(sample[0] == 0f, "invalid maximum range leaves value intact");
        }
        for (int i = 0; i < 10000; i++) {
            boolean proximity = (i % 8 == 0);
            float[] sample = {i + 0.25f, i + 1f};
            boolean changed = ProximityDispatchPolicy.replaceNearWithFar(proximity, 4.7f, sample);
            assertTrue(changed == proximity, "sensor classification iteration " + i);
            assertTrue(sample[0] == (proximity ? 4.7f : i + 0.25f), "distance iteration " + i);
            assertTrue(sample[1] == i + 1f, "other axis iteration " + i);
        }
        System.out.println("PASS: " + checked + " proximity-only distance assertions");
    }
}
