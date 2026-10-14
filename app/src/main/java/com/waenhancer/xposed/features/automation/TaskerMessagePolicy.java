package com.waenhancer.xposed.features.automation;

/**
 * Validates user-supplied automation extras before constructing a WhatsApp chat link.
 * Pure Java so the critical input rules can be tested without Android or DexKit.
 */
public final class TaskerMessagePolicy {
    public static final int MAX_PHONE_INPUT_CHARS = 64;
    public static final int MAX_MESSAGE_CHARS = 4096;
    private static final int MIN_PHONE_DIGITS = 7;
    private static final int MAX_PHONE_DIGITS = 15;

    private TaskerMessagePolicy() {}

    public static final class PreparedMessage {
        public final String phone;
        public final String text;
        private PreparedMessage(String phone, String text) {
            this.phone = phone;
            this.text = text;
        }
    }

    /**
     * Accept international phone numbers with familiar visual separators, and
     * legacy numeric @s.whatsapp.net / @c.us contact JIDs. Refuse @lid and
     * arbitrary suffixes; they are not interchangeable with telephone numbers.
     */
    public static PreparedMessage prepare(String rawNumber, String text) {
        if (rawNumber == null || text == null || rawNumber.length() > MAX_PHONE_INPUT_CHARS
                || text.length() > MAX_MESSAGE_CHARS || text.trim().isEmpty()
                || text.indexOf('\0') >= 0) return null;

        // Reject control characters before trim(), which would otherwise hide
        // CR/LF or tab injection in the recipient supplied by another app.
        for (int i = 0; i < rawNumber.length(); i++) {
            if (Character.isISOControl(rawNumber.charAt(i))) return null;
        }
        String candidate = rawNumber.trim();
        if (candidate.isEmpty()) return null;

        boolean fromJid = false;
        if (candidate.indexOf('@') >= 0) {
            String suffix = null;
            if (candidate.endsWith("@s.whatsapp.net")) suffix = "@s.whatsapp.net";
            else if (candidate.endsWith("@c.us")) suffix = "@c.us";
            if (suffix == null) return null;
            candidate = candidate.substring(0, candidate.length() - suffix.length());
            fromJid = true;
        }

        StringBuilder digits = new StringBuilder(candidate.length());
        for (int i = 0; i < candidate.length(); i++) {
            char ch = candidate.charAt(i);
            if (ch >= '0' && ch <= '9') {
                digits.append(ch);
            } else if (!fromJid && i == 0 && ch == '+') {
                // International dial prefix is optional in the input. The link
                // always uses the numeric form expected by WhatsApp.
            } else if (!fromJid && (ch == ' ' || ch == '-' || ch == '.' || ch == '(' || ch == ')')) {
                // Display formatting is allowed, but letters and URI operators are not.
            } else {
                return null;
            }
        }
        if (digits.length() < MIN_PHONE_DIGITS || digits.length() > MAX_PHONE_DIGITS) return null;
        return new PreparedMessage(digits.toString(), text);
    }

    /** Limits repeated external broadcasts from opening overlapping WhatsApp windows. */
    public static final class LaunchGate {
        private final long minimumIntervalMillis;
        private long lastLaunchAt = -1L;
        public LaunchGate(long minimumIntervalMillis) {
            if (minimumIntervalMillis <= 0L) throw new IllegalArgumentException("Invalid interval");
            this.minimumIntervalMillis = minimumIntervalMillis;
        }
        public synchronized boolean tryAcquire(long monotonicNowMillis) {
            if (monotonicNowMillis < 0L) return false;
            if (lastLaunchAt >= 0L && monotonicNowMillis >= lastLaunchAt
                    && monotonicNowMillis - lastLaunchAt < minimumIntervalMillis) return false;
            // If the monotonic clock resets, allow one fresh attempt.
            lastLaunchAt = monotonicNowMillis;
            return true;
        }
    }
}
