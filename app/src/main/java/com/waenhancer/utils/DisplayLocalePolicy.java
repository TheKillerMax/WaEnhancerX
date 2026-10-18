package com.waenhancer.utils;

import java.util.Locale;

/** Pure locale selection policy; never persists values or changes Locale.getDefault(). */
public final class DisplayLocalePolicy {
    private DisplayLocalePolicy() {}
    public static String canonicalCode(String code) {
        if (code == null || code.trim().isEmpty()) return "system";
        if (code.equals("es")) return "es-419"; // Keep existing app_language selections working.
        return code;
    }
    public static Locale resolve(String code, Locale system) {
        String canonical = canonicalCode(code);
        if (canonical.equals("system")) return system != null ? system : Locale.ENGLISH;
        if (canonical.equals("in")) return Locale.forLanguageTag("id-ID");
        Locale result = Locale.forLanguageTag(canonical);
        return result.getLanguage().isEmpty() ? (system != null ? system : Locale.ENGLISH) : result;
    }
}
