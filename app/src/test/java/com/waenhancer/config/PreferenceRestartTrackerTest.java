package com.waenhancer.config;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class PreferenceRestartTrackerTest {
    @Test
    public void publicFeatureSettingsRequireRestart() {
        assertTrue(PreferenceRestartTracker.requiresRestart("anti_revoke"));
        assertTrue(PreferenceRestartTracker.requiresRestart("floating_bottom_bar"));
    }

    @Test
    public void runtimeAndPrivateStateDoesNotRequireRestart() {
        assertFalse(PreferenceRestartTracker.requiresRestart("need_restart"));
        assertFalse(PreferenceRestartTracker.requiresRestart("pending_restart_changes"));
        assertFalse(PreferenceRestartTracker.requiresRestart("show_restart_sheet"));
        assertFalse(PreferenceRestartTracker.requiresRestart("active_xposed_api_version"));
        assertFalse(PreferenceRestartTracker.requiresRestart("assemblyai_key"));
        assertFalse(PreferenceRestartTracker.requiresRestart("unknown_key"));
    }

    @Test
    public void usesFeatureLabelsAndReadableFallbacks() {
        assertEquals("Anti-Revoke Messages",
                PreferenceRestartTracker.displayName("anti_revoke"));
        assertEquals("Show toast notification on delete message",
                PreferenceRestartTracker.displayName("toastdeleted"));
        assertEquals("Floating Bottom Bar Radius",
                PreferenceRestartTracker.displayName("floating_bottom_bar_radius"));
        assertEquals("DPI Mode", PreferenceRestartTracker.displayName("dpi_mode"));
    }
}
