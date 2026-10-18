package com.waenhancer.config;

import java.util.Objects;
import java.util.function.Predicate;

/** Keeps the DND hook and its controls consistent when legacy backups contain dndmode. */
public final class DndPreferencePolicy {
    private DndPreferencePolicy() {}

    public static boolean isEnabled(Predicate<String> contains, Predicate<String> readBoolean) {
        Objects.requireNonNull(contains, "contains");
        Objects.requireNonNull(readBoolean, "readBoolean");
        // Presence matters: an explicit current OFF must override an old ON.
        return readBoolean.test(contains.test("dnd_mode") ? "dnd_mode" : "dndmode");
    }
}
