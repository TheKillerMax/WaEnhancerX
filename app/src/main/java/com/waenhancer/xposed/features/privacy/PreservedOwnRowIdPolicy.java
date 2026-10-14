package com.waenhancer.xposed.features.privacy;

import java.util.Set;

/** Only a type-15 revoke placeholder may release a preserved outgoing row ID. */
final class PreservedOwnRowIdPolicy {
    private static final int REVOKE_PLACEHOLDER_TYPE = 15;

    private PreservedOwnRowIdPolicy() {}

    static boolean shouldStripPlaceholderId(Integer messageType, Long rowId,
                                            Set<String> preservedOwnRowIds) {
        return messageType != null && messageType == REVOKE_PLACEHOLDER_TYPE
                && rowId != null && preservedOwnRowIds != null
                && preservedOwnRowIds.remove(Long.toString(rowId));
    }
}
