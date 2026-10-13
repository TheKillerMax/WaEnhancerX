package com.waenhancer.config;

import java.util.Map;
import java.util.Set;

/** Verify persisted hook/legacy UI settings are included in versioned backups. */
public final class TestFeaturePreferenceSchemaCoverage {
    private static int count;
    private static void check(boolean value, String name) {count++;if(!value)throw new AssertionError(name);}
    public static void main(String[] args) {
        Map<String, PreferenceSchema.Type> required = Map.ofEntries(
                Map.entry("anti_revoke_color_enabled", PreferenceSchema.Type.BOOLEAN),
                Map.entry("bubble_colors", PreferenceSchema.Type.BOOLEAN),
                Map.entry("bubble_incoming_color", PreferenceSchema.Type.STRING),
                Map.entry("bubble_outgoing_color", PreferenceSchema.Type.STRING),
                Map.entry("call_privacy_enabled", PreferenceSchema.Type.BOOLEAN),
                Map.entry("call_recording", PreferenceSchema.Type.BOOLEAN),
                Map.entry("channels_enhancements", PreferenceSchema.Type.BOOLEAN),
                Map.entry("dndmode", PreferenceSchema.Type.BOOLEAN),
                Map.entry("download_view_once", PreferenceSchema.Type.BOOLEAN),
                Map.entry("enable_media_preview", PreferenceSchema.Type.BOOLEAN),
                Map.entry("hide_recording", PreferenceSchema.Type.BOOLEAN),
                Map.entry("hide_typing", PreferenceSchema.Type.BOOLEAN),
                Map.entry("media_upload_quality", PreferenceSchema.Type.BOOLEAN),
                Map.entry("open_wae", PreferenceSchema.Type.BOOLEAN),
                Map.entry("separate_groups_tabs", PreferenceSchema.Type.BOOLEAN),
                Map.entry("statusdowload", PreferenceSchema.Type.BOOLEAN),
                Map.entry("video_preview_muted", PreferenceSchema.Type.BOOLEAN)
        );
        for (Map.Entry<String, PreferenceSchema.Type> item : required.entrySet()) {
            String key = item.getKey();
            PreferenceSchema.Entry e = PreferenceSchema.entry(key);
            check(e != null, "missing schema key " + key);
            check(e.type == item.getValue(), "wrong type for " + key);
            check(e.store == PreferenceSchema.Store.PUBLIC, "wrong store for " + key);
            check(e.isExportable(), "not exportable " + key);
            check(PreferenceSchema.publicKeys().contains(key), "missing public index " + key);
            check(PreferenceSchema.exportableKeys().contains(key), "missing export index " + key);
        }
        check(!PreferenceSchema.isKnown("waex_pro_active"), "computed license state must not be exported");
        check(!PreferenceSchema.isKnown("pro_entitlement_unlock_wa_plus"), "computed entitlements must not be exported");
        System.out.println("PASS: " + count + " preference schema/type/backup index checks; exportable="
                + PreferenceSchema.exportableKeys().size());
    }
}
