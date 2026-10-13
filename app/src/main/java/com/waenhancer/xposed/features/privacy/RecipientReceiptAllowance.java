package com.waenhancer.xposed.features.privacy;

/**
 * Time-bounded, recipient-scoped permission for one explicit read-receipt ID.
 * A JID alone is never an authorization to disclose a read confirmation.
 * IDs use a null-delimited composite key; canonical JIDs cannot contain NUL.
 */
final class RecipientReceiptAllowance {
    private static final int MAX_RECEIPT_ID_LENGTH = 1024;
    private final BoundedReceiptAllowance grants;

    RecipientReceiptAllowance(long validForMillis, int maxKeys) {
        grants = new BoundedReceiptAllowance(validForMillis, maxKeys);
    }

    private static String qualifiedKey(String recipient, String messageId) {
        String exactJid = ReceiptJidPolicy.canonical(recipient);
        if (exactJid == null || messageId == null || messageId.isEmpty()
                || messageId.length() > MAX_RECEIPT_ID_LENGTH
                || messageId.indexOf('\0') >= 0) return null;
        return exactJid + "\0" + messageId;
    }

    void allow(String recipient, String messageId, long elapsedRealtimeMillis) {
        grants.allow(qualifiedKey(recipient, messageId), elapsedRealtimeMillis);
    }

    boolean isAllowed(String recipient, String messageId, long elapsedRealtimeMillis) {
        return grants.isAllowed(qualifiedKey(recipient, messageId), elapsedRealtimeMillis);
    }

    void revoke(String recipient, String messageId) {
        grants.revoke(qualifiedKey(recipient, messageId));
    }

    int countForTests() { return grants.countForTests(); }
}
