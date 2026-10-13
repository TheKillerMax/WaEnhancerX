package com.waenhancer.ui.screens.settings;

import java.util.Random;

public final class TestStyleNonBooleanPreferencePolicy {
    private static int assertions;
    private static void check(boolean yes, String description) {
        assertions++;
        if (!yes) throw new AssertionError(description);
    }
    public static void main(String[] args) {
        String[][] typed = {
            {"custom_theme", "STRING"},
            {"custom_view_dpi", "STRING"},
            {"chat_filters", "STRING"},
            {"hide_ui_tabs", "STRING_SET"},
            {"quick_home_menu", "STRING"}
        };
        for (String[] entry : typed) {
            check(StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(entry[0]), "Missing typed editor guard " + entry[0]);
            check(entry[1].equals(StyleNonBooleanPreferencePolicy.requiredKind(entry[0]).name()), "Wrong type " + entry[0]);
        }
        for (String key : new String[]{"custom_time_format", "custom_toolbar",
                "instagram_status_layout", "contact_blocked_verify", "seen_tick_customization",
                "seentick", "disable_sensor_proximity", "send_audio_as_voice_status",
                "bubble_colors", "custom_filters", "", "floating_bottom_bar"}) {
            check(!StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key), "Boolean/special setting blocked " + key);
        }
        check(!StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(null), "Null must not be a typed editor");
        Random r = new Random(0x57A73L);
        for (int i=0; i<100_000; i++) {
            String key = "other_" + r.nextLong();
            check(StyleNonBooleanPreferencePolicy.requiredKind(key) == StyleNonBooleanPreferencePolicy.Kind.NONE,
                    "Unexpected random key matched");
        }
        System.out.println("PASS: " + assertions + " typed Styles/no-op prevention policy checks");
    }
}
