package com.waenhancer.ui.screens.privacy;

import java.util.Locale;

/** Pure-Java conversion at the UI boundary for the schema's INT ARGB preference. */
public final class DeletedIndicatorPreferencePolicy {
    public static final String DEFAULT_COLOR_HEX = "#EF4444";

    private DeletedIndicatorPreferencePolicy() {}

    /** Read old hex strings and canonical int values without a SharedPreferences class cast. */
    public static String toColorHex(Object stored) {
        if (stored instanceof Number) {
            return String.format(Locale.ROOT, "#%08X", ((Number) stored).intValue());
        }
        if (stored instanceof String) {
            String raw = ((String) stored).trim();
            Integer color = toArgbOrNull(raw);
            if (color != null) return String.format(Locale.ROOT, "#%08X", color);
            // Legacy getString() could stringify integer ARGB values as signed decimal.
            try {
                return String.format(Locale.ROOT, "#%08X", Integer.parseInt(raw));
            } catch (NumberFormatException ignored) {
                return DEFAULT_COLOR_HEX;
            }
        }
        return DEFAULT_COLOR_HEX;
    }

    /** Decode #RRGGBB or #AARRGGBB. Invalid picker/backup values are rejected. */
    public static Integer toArgbOrNull(String selectedColor) {
        if (selectedColor == null) return null;
        String text = selectedColor.trim();
        if (text.length() != 7 && text.length() != 9) return null;
        if (text.charAt(0) != '#') return null;
        for (int i = 1; i < text.length(); i++) {
            if (Character.digit(text.charAt(i), 16) < 0) return null;
        }
        try {
            long color = Long.parseLong(text.substring(1), 16);
            if (text.length() == 7) color |= 0xFF000000L;
            return (int) color;
        } catch (NumberFormatException ignored) {
            return null;
        }
    }
}
