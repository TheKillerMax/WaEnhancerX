package com.waenhancer.xposed.features.privacy;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/** Monotonic-time, bounded allowance window for explicit read-receipt dispatch. */
final class BoundedReceiptAllowance {
    private final long validForMillis;
    private final int maxKeys;
    private final LinkedHashMap<String, Long> grants = new LinkedHashMap<>(32, 0.75f, true);

    BoundedReceiptAllowance(long validForMillis, int maxKeys) {
        if (validForMillis <= 0 || maxKeys <= 0) throw new IllegalArgumentException("Invalid allowance policy");
        this.validForMillis = validForMillis;
        this.maxKeys = maxKeys;
    }

    synchronized void allow(String key, long monotonicNowMillis) {
        if (key == null || key.isEmpty() || monotonicNowMillis < 0L) return;
        grants.put(key, monotonicNowMillis);
        if (grants.size() > maxKeys) {
            // Opportunistically purge expired grants first; no map growth on stale IDs.
            Iterator<Map.Entry<String, Long>> it = grants.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<String, Long> entry = it.next();
                long age = monotonicNowMillis - entry.getValue();
                if (age < 0 || age > validForMillis) it.remove();
            }
            while (grants.size() > maxKeys) {
                String oldest = grants.keySet().iterator().next();
                grants.remove(oldest);
            }
        }
    }

    synchronized boolean isAllowed(String key, long monotonicNowMillis) {
        if (key == null || monotonicNowMillis < 0L) return false;
        Long granted = grants.get(key);
        if (granted == null) return false;
        long age = monotonicNowMillis - granted;
        if (age >= 0L && age <= validForMillis) return true;
        grants.remove(key);
        return false;
    }

    synchronized void revoke(String key) {
        if (key != null) grants.remove(key);
    }

    synchronized int countForTests() { return grants.size(); }
}
