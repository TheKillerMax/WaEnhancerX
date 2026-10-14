package com.waenhancer.xposed.features.privacy;

import java.util.Collection;

/**
 * Resolves a manual-read target only when all supplied explicit JIDs agree.
 * Values must already be extracted from named, conversation-specific fields;
 * never pass unfiltered Activity object fields or arbitrary Intent extras.
 */
final class ConversationRecipientPolicy {
    private ConversationRecipientPolicy() {}

    static String resolve(Collection<String> candidates) {
        if (candidates == null || candidates.isEmpty()) return null;
        String selected = null;
        for (String raw : candidates) {
            String jid = ReceiptJidPolicy.canonical(raw);
            if (jid == null) return null;
            if (selected != null && !selected.equals(jid)) return null;
            selected = jid;
        }
        return selected;
    }
}
