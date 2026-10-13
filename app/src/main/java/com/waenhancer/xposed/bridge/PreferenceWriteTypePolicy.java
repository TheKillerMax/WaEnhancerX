package com.waenhancer.xposed.bridge;

/** Checks provider write types against known PreferenceSchema entries. */
final class PreferenceWriteTypePolicy {
    private PreferenceWriteTypePolicy() {}

    static boolean accepts(String declaredType, String writeType) {
        if ("remove".equals(writeType)) return true;
        if (declaredType == null || writeType == null) return false;
        switch (declaredType) {
            case "BOOLEAN": return "boolean".equals(writeType);
            case "STRING": return "string".equals(writeType);
            case "STRING_SET": return "string_set".equals(writeType);
            case "INT": return "int".equals(writeType);
            case "LONG": return "long".equals(writeType);
            case "FLOAT": return "float".equals(writeType);
            default: return false;
        }
    }
}
