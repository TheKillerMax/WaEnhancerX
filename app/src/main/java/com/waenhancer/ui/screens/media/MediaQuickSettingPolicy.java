package com.waenhancer.ui.screens.media;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.Predicate;

/**
 * Maps Media Hub quick controls to the settings actually consumed by Xposed hooks.
 *
 * <p>Legacy UI-only keys are written for compatibility, but are never used to infer
 * that recording or media hooks are enabled. In particular, an old ineffective
 * call_recording=true value must not silently enable recording on upgrade.</p>
 */
public final class MediaQuickSettingPolicy {
    private MediaQuickSettingPolicy() {}

    public static boolean isEnabled(String displayKey, Predicate<String> readEnabled) {
        Objects.requireNonNull(displayKey, "displayKey");
        Objects.requireNonNull(readEnabled, "readEnabled");
        switch (displayKey) {
            case "call_recording":
                return readEnabled.test("call_recording_enabled");
            case "media_upload_quality":
                // The two host hooks are independently gated; a single ON switch
                // must not claim both are enabled when only one preference is true.
                return readEnabled.test("imagequality") && readEnabled.test("video_maxfps");
            default:
                return readEnabled.test(displayKey);
        }
    }

    public static Map<String, Boolean> changesFor(String displayKey, boolean enabled) {
        Objects.requireNonNull(displayKey, "displayKey");
        if (displayKey.isEmpty()) throw new IllegalArgumentException("Empty preference key");
        Map<String, Boolean> changes = new LinkedHashMap<>();
        switch (displayKey) {
            case "call_recording":
                changes.put("call_recording_enabled", enabled);
                changes.put("call_recording", enabled); // legacy UI alias
                break;
            case "media_upload_quality":
                changes.put("imagequality", enabled);
                changes.put("video_maxfps", enabled);
                changes.put("media_upload_quality", enabled); // legacy UI alias
                break;
            case "statusdowload":
            case "status_downloader":
                changes.put("statusdowload", enabled);
                changes.put("status_downloader", enabled);
                break;
            case "downloadviewonce":
            case "download_view_once":
                changes.put("downloadviewonce", enabled);
                changes.put("download_view_once", enabled);
                break;
            case "media_preview":
            case "enable_media_preview":
                changes.put("enable_media_preview", enabled);
                changes.put("media_preview", enabled);
                break;
            case "send_audio_as_voice_status":
                changes.put("send_audio_as_voice_status", enabled);
                changes.put("voice_status_enhancement", enabled);
                break;
            default:
                changes.put(displayKey, enabled);
                break;
        }
        return Collections.unmodifiableMap(changes);
    }
}
