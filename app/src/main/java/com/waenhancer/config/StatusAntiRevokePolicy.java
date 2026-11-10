package com.waenhancer.config;

/** Converts the status Anti-Revoke value without changing the shared bridge's typed getters. */
public final class StatusAntiRevokePolicy {
    private StatusAntiRevokePolicy() {}

    /**
     * The UI writes the schema's String "1"/"0". Retain the same Boolean and numeric
     * legacy conversions as WaexPreferenceManager so the UI and hook agree.
     * Callers supply the canonical value from the bridge's target-resolved snapshot.
     */
    public static boolean isEnabled(Object value) {
        if (value instanceof Boolean) return (Boolean) value;
        if (value instanceof String) {
            return "1".equals(value) || "true".equalsIgnoreCase((String) value);
        }
        if (value instanceof Number) return ((Number) value).intValue() != 0;
        return false;
    }
}
