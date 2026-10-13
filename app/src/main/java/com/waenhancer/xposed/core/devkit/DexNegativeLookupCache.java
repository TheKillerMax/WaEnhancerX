package com.waenhancer.xposed.core.devkit;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * Process-local, capacity-bounded cooldown for unsuccessful DexKit resolutions.
 *
 * <p>Cached failures are deliberately never persisted: restarting the host or
 * clearing the cache always permits a fresh lookup. All timestamps should come
 * from a monotonic clock (Android's SystemClock.elapsedRealtime).</p>
 *
 * <p>The lock is held only for map access, never while running DexKit or
 * resolving reflective members.</p>
 */
final class DexNegativeLookupCache {
    enum Kind { CLASS, METHOD, FIELD }

    private final long retryAfterMillis;
    private final int maximumEntries;
    private final LinkedHashMap<String, Long> failures =
            new LinkedHashMap<>(128, 0.75f, true);

    DexNegativeLookupCache(long retryAfterMillis, int maximumEntries) {
        if (retryAfterMillis <= 0 || maximumEntries <= 0) {
            throw new IllegalArgumentException("Invalid cooldown or capacity");
        }
        this.retryAfterMillis = retryAfterMillis;
        this.maximumEntries = maximumEntries;
    }

    private static String scopedKey(Kind kind, String key) {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(key, "key");
        return kind.name() + ":" + key;
    }

    synchronized boolean shouldSkip(Kind kind, String key, long nowMillis) {
        String scoped = scopedKey(kind, key);
        Long failedAt = failures.get(scoped);
        if (failedAt == null) return false;
        // elapsedRealtime is monotonic; handle anomalous clock rollbacks safely.
        if (nowMillis >= failedAt && nowMillis - failedAt < retryAfterMillis) return true;
        failures.remove(scoped);
        return false;
    }

    synchronized void recordFailure(Kind kind, String key, long nowMillis) {
        failures.put(scopedKey(kind, key), nowMillis);
        while (failures.size() > maximumEntries) {
            String oldest = failures.keySet().iterator().next();
            failures.remove(oldest);
        }
    }

    synchronized void clearFailure(Kind kind, String key) {
        failures.remove(scopedKey(kind, key));
    }

    synchronized void clear() { failures.clear(); }

    synchronized int sizeForTests() { return failures.size(); }
}
