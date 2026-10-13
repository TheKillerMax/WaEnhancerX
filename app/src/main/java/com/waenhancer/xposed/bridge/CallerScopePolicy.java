package com.waenhancer.xposed.bridge;

import java.util.Arrays;
import java.util.Set;

/** Pure UID-to-package authorization policy, shared by all HookProvider.call routes. */
final class CallerScopePolicy {
    private CallerScopePolicy() {}

    static boolean isTrusted(int callerUid, int moduleUid, String[] packagesForUid, Set<String> supported) {
        if (callerUid == moduleUid) return true;
        if (packagesForUid == null || supported == null) return false;
        for (String packageName : packagesForUid) {
            if (supported.contains(packageName)) return true;
        }
        return false;
    }

    static boolean ownsPackage(int callerUid, int moduleUid, String[] packagesForUid, String requested) {
        if (callerUid == moduleUid) return true;
        return requested != null && !requested.isEmpty() && packagesForUid != null
                && Arrays.asList(packagesForUid).contains(requested);
    }
}
