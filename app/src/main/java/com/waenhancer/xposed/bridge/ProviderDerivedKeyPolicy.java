package com.waenhancer.xposed.bridge;

/** Protects provider-derived status and package telemetry from generic preference writes. */
final class ProviderDerivedKeyPolicy {
    private ProviderDerivedKeyPolicy() {}

    static boolean allowsGenericWrite(String key) {
        if (key == null || key.isEmpty()) return false;
        // Computed from the module's license state, never accepted from a target app.
        if ("waex_pro_active".equals(key) || key.startsWith("pro_entitlement_")) return false;
        // Only dedicated provider routes may update authenticated injection telemetry.
        if ("hooked_whatsapp_packages".equals(key)
                || key.startsWith("injected_hooks_")
                || key.startsWith("last_active_")) return false;
        // The module's own Activity hook records the framework API locally.
        if ("active_xposed_api_version".equals(key)) return false;
        return true;
    }
}
