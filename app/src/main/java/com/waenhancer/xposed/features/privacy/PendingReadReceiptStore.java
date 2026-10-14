package com.waenhancer.xposed.features.privacy;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Bounded pending read-receipt store; only the exact recipient can release a queue. */
final class PendingReadReceiptStore<T> {
    private final int maxRecipients;
    private final int maxPerRecipient;
    private final LinkedHashMap<String, ArrayDeque<T>> queues =
            new LinkedHashMap<>(16, 0.75f, true);

    PendingReadReceiptStore(int maxRecipients, int maxPerRecipient) {
        if (maxRecipients <= 0 || maxPerRecipient <= 0)
            throw new IllegalArgumentException("Both limits must be positive");
        this.maxRecipients = maxRecipients;
        this.maxPerRecipient = maxPerRecipient;
    }

    synchronized void add(String recipient, T job) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(job, "job");
        if (recipient.isEmpty()) throw new IllegalArgumentException("Empty recipient");
        ArrayDeque<T> pending = queues.computeIfAbsent(recipient, key -> new ArrayDeque<>());
        if (pending.size() == maxPerRecipient) pending.removeFirst();
        pending.addLast(job);
        while (queues.size() > maxRecipients) {
            String eldest = queues.keySet().iterator().next();
            queues.remove(eldest);
        }
    }

    synchronized List<T> drain(String recipient) {
        if (recipient == null || recipient.isEmpty()) return Collections.emptyList();
        ArrayDeque<T> pending = queues.remove(recipient);
        return pending == null ? Collections.emptyList() : new ArrayList<>(pending);
    }

    synchronized int pendingCount(String recipient) {
        ArrayDeque<T> pending = queues.get(recipient);
        return pending == null ? 0 : pending.size();
    }

    synchronized int recipientCount() { return queues.size(); }
}
