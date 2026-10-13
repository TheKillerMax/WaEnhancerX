package com.waenhancer.xposed.bridge;

public final class TestPreferenceWriteTypePolicy {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        String[] schemaTypes = {"BOOLEAN", "STRING", "STRING_SET", "INT", "LONG", "FLOAT"};
        String[] wireTypes = {"boolean", "string", "string_set", "int", "long", "float"};
        int count = 0;
        for (int i = 0; i < schemaTypes.length; i++) {
            for (int j = 0; j < wireTypes.length; j++) {
                boolean matched = PreferenceWriteTypePolicy.accepts(schemaTypes[i], wireTypes[j]);
                check(matched == (i == j), "invalid type pairing " + schemaTypes[i] + "/" + wireTypes[j]);
                count++;
            }
            check(PreferenceWriteTypePolicy.accepts(schemaTypes[i], "remove"), "remove is type-independent");
            count++;
        }
        check(!PreferenceWriteTypePolicy.accepts("BOOLEAN", "string"),
                "boolean gate must not be bypassed with a string-encoded true");
        check(!PreferenceWriteTypePolicy.accepts("STRING", "boolean"), "string setting cannot be overwritten with a boolean");
        check(!PreferenceWriteTypePolicy.accepts(null, "string"), "null schema type rejected");
        check(!PreferenceWriteTypePolicy.accepts("BOOLEAN", null), "null wire type rejected");
        check(!PreferenceWriteTypePolicy.accepts("NEW_TYPE", "string"), "future schema types fail closed");
        System.out.println("PASS: " + count + " known-type and removal combinations plus negative controls");
    }
}
