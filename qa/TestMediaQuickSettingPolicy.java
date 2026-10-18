package com.waenhancer.ui.screens.media;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** JDK-only regression harness for the production Media Hub quick-toggle policy. */
public final class TestMediaQuickSettingPolicy {
    private static int checks;
    private static void check(boolean condition, String why) {
        checks++;
        if (!condition) throw new AssertionError(why);
    }
    private static boolean enabled(String key, Map<String, Boolean> stored) {
        return MediaQuickSettingPolicy.isEnabled(key, k -> stored.getOrDefault(k, false));
    }
    private static void expectWrites(String key, boolean value, String... expectedKeys) {
        Map<String, Boolean> changes = MediaQuickSettingPolicy.changesFor(key, value);
        check(changes.size() == expectedKeys.length, key + ": unexpected changes " + changes);
        check(Arrays.asList(expectedKeys).equals(Arrays.asList(changes.keySet().toArray(new String[0]))),
                key + ": keys/order differ " + changes.keySet());
        check(changes.values().stream().allMatch(v -> v == value), key + ": wrong value");
        try {
            changes.clear();
            throw new AssertionError("mutable change set");
        } catch (UnsupportedOperationException expected) { checks++; }
    }
    public static void main(String[] args) {
        // Existing canonical setting always wins over stale legacy UI-only aliases.
        Map<String, Boolean> flags = new LinkedHashMap<>();
        flags.put("call_recording", true);
        flags.put("media_upload_quality", true);
        check(!enabled("call_recording", flags), "never silently enable recording from old alias");
        check(!enabled("media_upload_quality", flags), "old HD alias cannot claim hooks are on");
        flags.put("call_recording_enabled", true);
        check(enabled("call_recording", flags), "actual recorder setting must be reflected");
        flags.put("call_recording", false);
        check(enabled("call_recording", flags), "stale legacy recorder flag is irrelevant");
        flags.put("imagequality", true);
        check(!enabled("media_upload_quality", flags), "one of two hooks is not full HD preset");
        flags.put("video_maxfps", true);
        check(enabled("media_upload_quality", flags), "both underlying flags active");
        flags.put("imagequality", false);
        check(!enabled("media_upload_quality", flags), "one flag disabled");
        flags.put("imagequality", true);
        flags.put("video_maxfps", false);
        check(!enabled("media_upload_quality", flags), "second flag disabled");

        // Privacy and Media render download_view_once; the hook reads downloadviewonce.
        flags.put("download_view_once", true);
        check(!enabled("download_view_once", flags), "display-only alias cannot claim active downloader");
        flags.put("downloadviewonce", true);
        flags.put("download_view_once", false);
        check(enabled("download_view_once", flags), "catalogue entry reads actual enabled hook key");
        flags.put("downloadviewonce", false);
        flags.put("download_view_once", true);
        check(!enabled("download_view_once", flags), "explicit hook-off wins stale display alias");
        for (String entry : new String[]{"downloadviewonce", "download_view_once"}) {
            for (boolean state : new boolean[]{true, false, true}) {
                flags.putAll(MediaQuickSettingPolicy.changesFor(entry, state));
                Map<String, Boolean> reopened = new LinkedHashMap<>(flags);
                check(enabled("download_view_once", reopened) == state, "recreated Privacy/Media state");
                check(enabled("downloadviewonce", reopened) == state, "runtime downloader state");
            }
        }

        expectWrites("call_recording", true, "call_recording_enabled", "call_recording");
        expectWrites("call_recording", false, "call_recording_enabled", "call_recording");
        expectWrites("media_upload_quality", true, "imagequality", "video_maxfps", "media_upload_quality");
        expectWrites("media_upload_quality", false, "imagequality", "video_maxfps", "media_upload_quality");
        expectWrites("statusdowload", true, "statusdowload", "status_downloader");
        expectWrites("status_downloader", false, "statusdowload", "status_downloader");
        expectWrites("downloadviewonce", true, "downloadviewonce", "download_view_once");
        expectWrites("download_view_once", false, "downloadviewonce", "download_view_once");
        expectWrites("media_preview", true, "enable_media_preview", "media_preview");
        expectWrites("enable_media_preview", false, "enable_media_preview", "media_preview");
        expectWrites("send_audio_as_voice_status", true, "send_audio_as_voice_status", "voice_status_enhancement");
        expectWrites("download_profile", false, "download_profile");
        check(!MediaQuickSettingPolicy.changesFor("media_upload_quality", true).containsKey("videoquality"),
                "do not write unrelated legacy video quality toggle");

        for (int bitmask = 0; bitmask < 8; ++bitmask) {
            flags.put("media_upload_quality", (bitmask & 1) != 0);
            flags.put("imagequality", (bitmask & 2) != 0);
            flags.put("video_maxfps", (bitmask & 4) != 0);
            check(enabled("media_upload_quality", flags) == ((bitmask & 6) == 6), "composite setting state " + bitmask);
        }
        // Repeated enable/disable sequences converge without stale state.
        for (int i = 0; i < 3000; ++i) {
            boolean state = i % 2 == 0;
            flags.putAll(MediaQuickSettingPolicy.changesFor("media_upload_quality", state));
            check(enabled("media_upload_quality", flags) == state, "toggle round-trip #" + i);
            flags.putAll(MediaQuickSettingPolicy.changesFor("call_recording", state));
            check(enabled("call_recording", flags) == state, "recording round-trip #" + i);
        }
        check(!enabled("download_profile", Collections.emptyMap()), "unchanged key still reads its own state");
        try {
            MediaQuickSettingPolicy.changesFor("", true);
            throw new AssertionError("empty key accepted");
        } catch (IllegalArgumentException expected) { checks++; }
        try {
            MediaQuickSettingPolicy.isEnabled(null, k -> false);
            throw new AssertionError("null key accepted");
        } catch (NullPointerException expected) { checks++; }
        System.out.println("PASS: " + checks + " Media Hub mapping/compatibility checks");
    }
}
