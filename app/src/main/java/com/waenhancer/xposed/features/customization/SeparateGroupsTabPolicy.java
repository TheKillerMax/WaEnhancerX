package com.waenhancer.xposed.features.customization;

import java.util.ArrayList;
import java.util.List;

final class SeparateGroupsTabPolicy {
    private static final int GROUPS = 500;
    private static final int COMMUNITIES = 600;
    private static final int MAX_BOTTOM_BAR_ITEMS = 5;

    private SeparateGroupsTabPolicy() {}

    static ArrayList<Integer> rewrite(List<Integer> nativeTabs) {
        ArrayList<Integer> result = new ArrayList<>(nativeTabs);
        result.removeIf(id -> id != null && id == GROUPS);
        result.removeIf(id -> id != null && id == COMMUNITIES);
        if (result.size() < MAX_BOTTOM_BAR_ITEMS) {
            result.add(Math.min(1, result.size()), GROUPS);
        }
        return result;
    }
}
