package com.waenhancer.ui.screens.settings;

public final class TestManualSeenTickPreferencePolicy {
    private static int count;
    private static void check(boolean ok, String message) {
        count++;
        if (!ok) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        for (String text : new String[]{null, "", "0", "false", "FALSE", "3", "random"}) {
            check(!ManualSeenTickPreferencePolicy.isEnabled(text), "not enabled by " + text);
        }
        for (String text : new String[]{"1", "2", "true", "TRUE"}) {
            check(ManualSeenTickPreferencePolicy.isEnabled(text), "enabled by " + text);
        }
        check("0".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(false, "2")), "disable overflow");
        check("0".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(false, "true")), "disable legacy");
        check("2".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(true, "2")), "preserve overflow");
        check("1".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(true, "0")), "enable toolbar");
        check("1".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(true, "true")), "normalize legacy");
        check("1".equals(ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(true, null)), "unset stays disabled until user enables");
        System.out.println("PASS: " + count + " manual blue-tick UI mapping assertions");
    }
}
