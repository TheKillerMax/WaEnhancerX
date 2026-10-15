package com.waenhancer.ui.screens.privacy;

public final class TestDeletedIndicatorPreferencePolicy {
    private static int checks;
    private static void check(boolean ok, String description) {
        checks++;
        if (!ok) throw new AssertionError(description);
    }
    public static void main(String[] args) {
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#EF4444") == 0xFFEF4444, "opaque default red");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#80Aa01fe") == 0x80AA01FE, "eight-digit alpha");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#000000") == 0xFF000000, "opaque black");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#FFFFFFFF") == -1, "opaque white");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull(" #ABCDEF ") == 0xFFABCDEF, "trim safely");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#FFFF") == null, "invalid length");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#GFFFFF") == null, "non-hex rejected");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("FFFFFF") == null, "missing hash rejected");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("") == null, "empty rejected");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull(null) == null, "null rejected");
        check(DeletedIndicatorPreferencePolicy.toArgbOrNull("#FFFFFF00AB") == null, "oversized rejected");
        check("#FFEF4444".equals(DeletedIndicatorPreferencePolicy.toColorHex((int) 0xFFEF4444)), "canonical INT decoded");
        check("#FFEF4444".equals(DeletedIndicatorPreferencePolicy.toColorHex("#EF4444")), "legacy 6-char string decoded");
        check("#80112233".equals(DeletedIndicatorPreferencePolicy.toColorHex("#80112233")), "legacy alpha string decoded");
        check(DeletedIndicatorPreferencePolicy.toColorHex(-1096636).startsWith("#FF"), "signed negative colors handled");
        check(DeletedIndicatorPreferencePolicy.DEFAULT_COLOR_HEX.equals(DeletedIndicatorPreferencePolicy.toColorHex("bad")), "invalid color falls back");
        check(DeletedIndicatorPreferencePolicy.DEFAULT_COLOR_HEX.equals(DeletedIndicatorPreferencePolicy.toColorHex(null)), "null falls back");
        check(DeletedIndicatorPreferencePolicy.DEFAULT_COLOR_HEX.equals(DeletedIndicatorPreferencePolicy.toColorHex(new Object())), "unsupported type falls back");
        for (int value : new int[]{0, 0xFF000000, 0xFF123456, 0x00FFFFFF, 0x80ABCDEF, 0x7F000001, 0xFFFFFFFF}) {
            String hex = DeletedIndicatorPreferencePolicy.toColorHex(value);
            check(DeletedIndicatorPreferencePolicy.toArgbOrNull(hex).intValue() == value, "INT/hex round-trip " + hex);
        }
        System.out.println("PASS: " + checks + " deleted-indicator color type/compatibility assertions");
    }
}
