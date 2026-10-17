package com.waenhancer.xposed.features.privacy;

import java.util.regex.Pattern;

/**
 * Exact, fail-closed JID normalization shared by deferred read receipt hooks.
 *
 * Never search arbitrary object toString()/Intent text for a substring: the
 * selected JID controls which conversation's held read receipts may be sent.
 * Distinct LID, phone, group, and broadcast namespaces must remain distinct.
 */
final class ReceiptJidPolicy {
    private static final int MAX_JID_LENGTH = 128;
    private static final Pattern COMPLETE_JID = Pattern.compile(
            "[0-9]+(?:-[0-9]+)?@(s\\.whatsapp\\.net|g\\.us|lid|broadcast)");

    private ReceiptJidPolicy() {}

    /** Return an unmodified exact JID or null; never infer a recipient. */
    static String canonical(String raw) {
        if (raw == null || raw.isEmpty() || raw.length() > MAX_JID_LENGTH) return null;
        return COMPLETE_JID.matcher(raw).matches() ? raw : null;
    }
}
