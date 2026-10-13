package com.waenhancer.xposed.features.privacy;

/**
 * One-shot thread-local handoff from a status database read to UI decoration.
 * A consumed key is immediately cleared, preventing reuse for a later status.
 * This does not establish a link between a query and a fragment on other threads.
 */
final class StatusKeyHandoff {
    private static final ThreadLocal<String> LATEST = new ThreadLocal<>();

    private StatusKeyHandoff() {}

    static void record(String keyId) {
        if (keyId == null || keyId.isEmpty()) LATEST.remove();
        else LATEST.set(keyId);
    }

    static String consume() {
        String value = LATEST.get();
        LATEST.remove();
        return value;
    }
}
