package com.waenhancer.utils;

import java.util.regex.Pattern;

/** Namespace-aware display lookup only. Never authenticates a sender or invents LID/phone links. */
public final class ContactIdentityPolicy {
    private ContactIdentityPolicy() {}
    private static final Pattern PHONE = Pattern.compile("[0-9]{5,15}@s\\.whatsapp\\.net");
    private static final Pattern LID = Pattern.compile("[0-9]{1,30}@lid");
    private static final Pattern GROUP = Pattern.compile("[0-9]{1,30}(?:-[0-9]{1,30})?@g\\.us");

    public static String canonicalJid(String value) {
        if (value == null || value.length() > 72) return null;
        return PHONE.matcher(value).matches() || LID.matcher(value).matches()
                || GROUP.matcher(value).matches() ? value : null;
    }
    public static boolean isLid(String value) {
        return value != null && value.length() <= 34 && LID.matcher(value).matches();
    }
    public static boolean isGroup(String value) {
        return value != null && value.length() <= 67 && GROUP.matcher(value).matches();
    }
    public static String phoneUser(String jid) {
        return jid != null && PHONE.matcher(jid).matches() ? jid.substring(0, jid.indexOf('@')) : null;
    }
    /** Full digits only; formatting separators do not authorize a suffix or country-code guess. */
    public static String phoneDigits(String value) {
        if (value == null || value.isEmpty() || value.length() > 40) return null;
        StringBuilder digits = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c >= '0' && c <= '9') digits.append(c);
            else if (c == '+' && i == 0) { }
            else if (c == ' ' || c == '-' || c == '(' || c == ')' || c == '.') { }
            else return null;
        }
        return digits.length() >= 5 && digits.length() <= 15 ? digits.toString() : null;
    }
}
