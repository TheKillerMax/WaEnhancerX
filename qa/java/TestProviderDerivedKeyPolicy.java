package com.waenhancer.xposed.bridge;

public final class TestProviderDerivedKeyPolicy {
    private static int tests;
    private static void check(boolean result, String reason) {
        tests++;
        if (!result) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        for (String key : new String[]{
            "waex_pro_active", "pro_entitlement_audio_to_voice_status",
            "pro_entitlement_unlock_wa_plus", "pro_entitlement_custom_flag",
            "hooked_whatsapp_packages", "injected_hooks_com.whatsapp",
            "injected_hooks_time_com.whatsapp", "last_active_com.whatsapp",
            "active_xposed_api_version"
        }) check(!ProviderDerivedKeyPolicy.allowsGenericWrite(key), "protected key accepted: " + key);
        for (String key : new String[]{
            "anti_revoke", "toastdeleted", "imagequality", "video_maxfps",
            "custom_css", "separategroups", "downloadstatus", "voice_status_enhancement",
            "legacy_compatible_setting"
        }) check(ProviderDerivedKeyPolicy.allowsGenericWrite(key), "normal key rejected: " + key);
        check(!ProviderDerivedKeyPolicy.allowsGenericWrite(null), "null key");
        check(!ProviderDerivedKeyPolicy.allowsGenericWrite(""), "empty key");
        System.out.println("PASS: " + tests + " reserved-vs-normal key checks");
    }
}
