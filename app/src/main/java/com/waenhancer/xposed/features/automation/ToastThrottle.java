package com.waenhancer.xposed.features.automation;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/** Bounded, synchronized per-event toast throttling without retaining contact identifiers indefinitely. */
final class ToastThrottle {
    private final long intervalMillis;
    private final int capacity;
    private final Map<String, Long> recent = new LinkedHashMap<>(64, 0.75f, true);

    ToastThrottle(long intervalMillis, int capacity) {
        if (intervalMillis < 0L || capacity < 1) throw new IllegalArgumentException();
        this.intervalMillis = intervalMillis;
        this.capacity = capacity;
    }

    synchronized boolean shouldEmit(String key, long now) {
        if (key == null || key.isEmpty()) return false;
        Long last = recent.get(key);
        if (last != null && now >= last && now - last < intervalMillis) return false;
        recent.put(key, now);
        if (recent.size() > capacity) {
            Iterator<String> it = recent.keySet().iterator();
            if (it.hasNext()) { it.next(); it.remove(); }
        }
        return true;
    }

    synchronized int trackedCountForTests() { return recent.size(); }
}
