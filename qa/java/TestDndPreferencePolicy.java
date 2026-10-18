package com.waenhancer.config;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class TestDndPreferencePolicy {
    private static int checks;

    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    private static boolean active(Map<String, Boolean> values) {
        return DndPreferencePolicy.isEnabled(values::containsKey, key -> values.getOrDefault(key, false));
    }

    public static void main(String[] args) {
        // Every combination of absence, false and true for both generations.
        Boolean[] values = {null, false, true};
        for (Boolean canonical : values) {
            for (Boolean legacy : values) {
                Map<String, Boolean> prefs = new LinkedHashMap<>();
                if (canonical != null) prefs.put("dnd_mode", canonical);
                if (legacy != null) prefs.put("dndmode", legacy);
                boolean expected = canonical != null ? canonical : Boolean.TRUE.equals(legacy);
                check(active(prefs) == expected, "canonical=" + canonical + ", legacy=" + legacy);
                Map<String, Boolean> before = new LinkedHashMap<>(prefs);
                active(prefs);
                check(prefs.equals(before), "reads must not migrate/reset preferences");
            }
        }
        Map<String, Boolean> upgraded = new LinkedHashMap<>();
        upgraded.put("dndmode", true);
        check(active(upgraded), "legacy-only enabled state remains visible");
        upgraded.put("dnd_mode", !active(upgraded));
        check(!active(upgraded), "one toggle turns legacy DND off");
        check(upgraded.get("dndmode"), "legacy storage is preserved, not destructively cleared");
        check(!active(new LinkedHashMap<>(upgraded)), "recreation keeps canonical OFF");
        upgraded.put("dnd_mode", true);
        check(active(upgraded), "explicit re-enable still works");
        AtomicInteger contains = new AtomicInteger(), reads = new AtomicInteger();
        for (int i = 0; i < 10000; i++) {
            check(!DndPreferencePolicy.isEnabled(key -> { contains.incrementAndGet(); return true; },
                    key -> { reads.incrementAndGet(); return !"dnd_mode".equals(key); }),
                    "canonical OFF must not consult legacy ON");
        }
        check(contains.get() == 10000 && reads.get() == 10000,
                "constant-time lookup: one presence and one Boolean read per decision");
        System.out.println("PASS: " + checks + " DND precedence and toggle checks");
    }
}
