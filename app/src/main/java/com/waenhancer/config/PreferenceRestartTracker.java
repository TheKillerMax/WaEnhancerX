package com.waenhancer.config;

import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/** Records user-facing feature names that require the hooked app to restart. */
public final class PreferenceRestartTracker {
    public static final String NEED_RESTART = "need_restart";
    public static final String PENDING_CHANGES = "pending_restart_changes";

    private PreferenceRestartTracker() {}


    public static synchronized void onPreferenceChanged(
            @NonNull SharedPreferences preferences, @Nullable String key) {
        if (!requiresRestart(key)) return;

        Set<String> pending = new LinkedHashSet<>(preferences.getStringSet(
                PENDING_CHANGES, java.util.Collections.emptySet()));
        // Store the stable key and resolve its current UI title when the sheet is built.
        pending.add(key);
        preferences.edit()
                .putStringSet(PENDING_CHANGES, pending)
                .putBoolean(NEED_RESTART, true)
                .apply();
    }

    public static boolean requiresRestart(@Nullable String key) {
        if (key == null || NEED_RESTART.equals(key) || PENDING_CHANGES.equals(key)) return false;
        PreferenceSchema.Entry entry = PreferenceSchema.entry(key);
        return entry != null
                && entry.store == PreferenceSchema.Store.PUBLIC
                && entry.sensitivity == PreferenceSchema.Sensitivity.PUBLIC_SETTING;
    }

    @NonNull
    public static String displayName(@NonNull String key) {
        String known = FeatureCatalog.getTitle(key);
        if (known != null) return known;

        String[] words = key.replace('-', '_').split("_+");
        StringBuilder result = new StringBuilder();
        for (String word : words) {
            if (word.isEmpty()) continue;
            if (result.length() > 0) result.append(' ');
            if ("ai".equalsIgnoreCase(word) || "hd".equalsIgnoreCase(word)
                    || "dpi".equalsIgnoreCase(word) || "dnd".equalsIgnoreCase(word)) {
                result.append(word.toUpperCase(Locale.ROOT));
            } else {
                result.append(Character.toUpperCase(word.charAt(0)));
                if (word.length() > 1) result.append(word.substring(1));
            }
        }
        return result.length() == 0 ? key : result.toString();
    }
}
