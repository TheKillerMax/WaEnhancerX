package com.waenhancer.ui.screens.settings;

/**
 * These catalog entries describe typed configuration values, not Boolean flags.
 * Do not allow the general Styles switch to read or write their UI alias keys.
 * The actual value must eventually be set through a dedicated typed editor.
 */
public final class StyleNonBooleanPreferencePolicy {
    public enum Kind { NONE, STRING, STRING_SET }

    private StyleNonBooleanPreferencePolicy() {}

    public static Kind requiredKind(String uiKey) {
        if (uiKey == null) return Kind.NONE;
        switch (uiKey) {
            case "custom_theme":
            case "custom_view_dpi":
            case "chat_filters":
            case "quick_home_menu":
                return Kind.STRING;
            case "hide_ui_tabs":
                return Kind.STRING_SET;
            default:
                return Kind.NONE;
        }
    }

    public static boolean requiresDedicatedEditor(String uiKey) {
        return requiredKind(uiKey) != Kind.NONE;
    }
}
