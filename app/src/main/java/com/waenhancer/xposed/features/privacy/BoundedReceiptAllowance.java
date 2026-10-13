package com.waenhancer.xposed.features.privacy;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/** Monotonic-time, bounded allowance window for explicit read-receipt dispatch. */
final class BoundedReceiptAllowance {
    private final long validForMillis;
    private final int maxKeys;
    private static final class Grant {
        long lastAllowed;
        int references;
        Grant(long time) { lastAllowed = time; references = 1; }
    }

    private final LinkedHashMap<String, Grant> grants = new LinkedHashMap<>(32, 0.75f, true);

    BoundedReceiptAllowance(long validForMillis, int maxKeys) {
        if (validForMillis <= 0 || maxKeys <= 0) throw new IllegalArgumentException("Invalid allowance policy");
        this.validForMillis = validForMillis;
        this.maxKeys = maxKeys;
    }

    synchronized void allow(String key, long monotonicNowMillis) {
        if (key == null || key.isEmpty() || monotonicNowMillis < 0L) return;
        Grant current = grants.get(key);
        if (current != null && monotonicNowMillis >= current.lastAllowed
                && monotonicNowMillis - current.lastAllowed <= validForMillis) {
            if (current.references < Integer.MAX_VALUE) current.references++;
            current.lastAllowed = monotonicNowMillis;
        } else {
            grants.put(key, new Grant(monotonicNowMillis));
        }
        if (grants.size() > maxKeys) {
            // Opportunistically purge expired grants first; no map growth on stale IDs.
            Iterator<Map.Entry<String, Grant>> it = grants.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<String, Grant> entry = it.next();
                long age = monotonicNowMillis - entry.getValue().lastAllowed;
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
        Grant granted = grants.get(key);
        if (granted == null) return false;
        long age = monotonicNowMillis - granted.lastAllowed;
        if (age >= 0L && age <= validForMillis) return true;
        grants.remove(key);
        return false;
    }

    synchronized void revoke(String key) {
        if (key == null) return;
        Grant current = grants.get(key);
        if (current == null) return;
        if (current.references <= 1) grants.remove(key);
        else current.references--;
    }

    synchronized int countForTests() { return grants.size(); }
}
