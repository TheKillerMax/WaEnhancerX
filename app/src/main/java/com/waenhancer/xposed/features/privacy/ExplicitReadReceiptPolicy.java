package com.waenhancer.xposed.features.privacy;

/**
 * A manual read allowance only exempts an actual read stanza. It must never
 * bypass delivery hiding or Ghost Mode (both expressed by hideDelivery=true).
 * Status receipts are handled separately and are not read exceptions.
 */
final class ExplicitReadReceiptPolicy {
    private ExplicitReadReceiptPolicy() {}

    static boolean maySend(String type, String recipient, String messageId,
                           boolean hideDelivery, RecipientReceiptAllowance grants,
                           long monotonicNowMillis) {
        return !hideDelivery && "read".equals(type) && grants != null
                && grants.isAllowed(recipient, messageId, monotonicNowMillis);
    }
}
