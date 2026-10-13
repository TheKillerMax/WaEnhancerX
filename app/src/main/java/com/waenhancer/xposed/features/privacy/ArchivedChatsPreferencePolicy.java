package com.waenhancer.xposed.features.privacy;

/** Compatible conversion for the historical STRING typearchive preference. */
public final class ArchivedChatsPreferencePolicy {
    private ArchivedChatsPreferencePolicy() {}

    public static boolean isHidden(Object value) {
        if (value instanceof Boolean) return (Boolean) value;
        if (value instanceof Number) return ((Number) value).intValue() != 0;
        if (!(value instanceof String)) return false;
        String text = ((String) value).trim();
        return !text.isEmpty() && !"0".equals(text) && !"false".equalsIgnoreCase(text);
    }
}
