package com.waenhancer.xposed.features.privacy;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

public final class TestPreservedOwnRevoke {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        Set<String> rows = Collections.synchronizedSet(new HashSet<>());
        rows.add("71");
        check(!PreservedOwnRowIdPolicy.shouldStripPlaceholderId(0, 71L, rows),
                "ordinary message cannot consume the preserved ID");
        check(rows.contains("71"), "ordinary insert must leave ID pending");
        check(!PreservedOwnRowIdPolicy.shouldStripPlaceholderId(null, 71L, rows),
                "missing type must leave ID pending");
        check(!PreservedOwnRowIdPolicy.shouldStripPlaceholderId(15, null, rows),
                "missing row ID must be ignored");
        check(!PreservedOwnRowIdPolicy.shouldStripPlaceholderId(15, 72L, rows),
                "unreserved row ID must be ignored");
        check(rows.contains("71"), "unrelated inserts must not consume the reservation");
        check(PreservedOwnRowIdPolicy.shouldStripPlaceholderId(15, 71L, rows),
                "own revoke placeholder must get a fresh SQLite row ID");
        check(!rows.contains("71"), "successful consumption must release the reservation");
        check(!PreservedOwnRowIdPolicy.shouldStripPlaceholderId(15, 71L, rows),
                "one-time reservation cannot be consumed twice");
        rows.add("-5");
        check(PreservedOwnRowIdPolicy.shouldStripPlaceholderId(15, -5L, rows),
                "ID representation must match SQLite signed long values");
        System.out.println("PASS: preserve original row and strip only type-15 revoke placeholder IDs");
    }
}
