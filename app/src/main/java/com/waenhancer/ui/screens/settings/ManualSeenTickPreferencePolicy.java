package com.waenhancer.ui.screens.settings;

/** Maps the manual-read-receipt UI switch to the hook's typed "seentick" setting. */
public final class ManualSeenTickPreferencePolicy {
    private ManualSeenTickPreferencePolicy() {}

    /** 0=off, 1=toolbar, 2=overflow menu. Support existing Boolean legacy values on read. */
    public static boolean isEnabled(String value) {
        return "1".equals(value) || "2".equals(value) || "true".equalsIgnoreCase(value);
    }

    /** Only an explicit user toggle may enable manual read receipt actions. */
    public static String valueAfterExplicitToggle(boolean enabled, String existing) {
        if (!enabled) return "0";
        // Preserve a user's existing overflow-menu preference instead of forcing toolbar mode.
        return "2".equals(existing) ? "2" : "1";
    }
}
