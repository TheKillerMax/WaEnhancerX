package com.waenhancer.config;

import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import java.util.LinkedHashSet;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Records user-facing feature names that require the hooked app to restart. */
public final class PreferenceRestartTracker {
    public static final String NEED_RESTART = "need_restart";
    public static final String PENDING_CHANGES = "pending_restart_changes";

    private static final Map<String, String> LABELS = createLabels();

    private PreferenceRestartTracker() {}

    private static Map<String, String> createLabels() {
        Map<String, String> labels = new HashMap<>();
        labels.put("always_online", "Always Online");
        labels.put("freezelastseen", "Freeze Last Seen");
        labels.put("freeze_last_seen", "Freeze Last Seen");
        labels.put("ghostmode_t", "Hide Typing");
        labels.put("ghostmode_r", "Hide Recording Audio");
        labels.put("hide_read_receipts", "Hide Blue Ticks");
        labels.put("hideread_group", "Hide Blue Ticks in Groups");
        labels.put("anti_revoke", "Anti-Revoke Messages");
        labels.put("antirevoke", "Anti-Revoke Messages");
        labels.put("anti_view_once", "Unlimited View Once");
        labels.put("status_downloader", "Download and Share Status");
        labels.put("downloadstatus", "Download and Share Status");
        labels.put("media_upload_quality", "HD Quality Images and Videos");
        labels.put("send_audio_as_voice_status", "Audio to Voice Status");
        labels.put("call_recording", "Call Recording");
        labels.put("voice_transcription", "Audio Transcription");
        labels.put("floating_bottom_bar", "Floating Bottom Bar");
        labels.put("separate_groups_tabs", "Separate Groups");
        labels.put("dotonline", "Online Dot in Conversation List");
        labels.put("showonlinetext", "Online and Last Seen in Conversation List");
        labels.put("show_hook_toast", "Hook Injection Toast");
        labels.put("bypass_version_check", "Version Check");
        labels.put("bootloader_spoofer", "Bootloader Spoofer");
        labels.put("custom_css", "Custom Theme CSS");
        labels.put("custom_theme", "Custom Theme CSS");
        labels.put("change_dpi", "WhatsApp Display Size");
        labels.put("custom_view_dpi", "WhatsApp Display Size");
        labels.put("restartbutton", "Restart Button");
        labels.put("open_wae", "WaEnhancer Button");
        labels.put("open_waex", "WaEnhancer Button");
        return java.util.Collections.unmodifiableMap(labels);
    }

    public static synchronized void onPreferenceChanged(
            @NonNull SharedPreferences preferences, @Nullable String key) {
        if (!requiresRestart(key)) return;

        Set<String> pending = new LinkedHashSet<>(preferences.getStringSet(
                PENDING_CHANGES, java.util.Collections.emptySet()));
        pending.add(displayName(key));
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
        String known = LABELS.get(key);
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
