package com.waenhancer.xposed.features.automation;

import java.util.regex.Pattern;

/** Explicit MessageHandler envelope observed in the reviewed 2.26.39.79 DEX.
 * Unknown events are ignored, not reinterpreted as an offline transition.
 * Other host versions require independent contract validation.
 */
public final class PresenceEventPolicy {
    public static final int EVENT_FAMILY = 5;
    public static final int AVAILABLE = 5;
    public static final int UNAVAILABLE = 64;
    private static final Pattern CONTACT_JID = Pattern.compile(
            "[0-9]+(?::[0-9]+)?@(s\\.whatsapp\\.net|whatsapp\\.net|lid)");

    private PresenceEventPolicy() {}

    public static final class Event {
        public final String jid;
        public final boolean online;
        private Event(String jid, boolean online) { this.jid = jid; this.online = online; }
    }

    public static boolean isPresenceCode(int code) {
        return code == AVAILABLE || code == UNAVAILABLE;
    }

    public static Event decode(int what, int code, Object rawJid, Object presence) {
        if (what != EVENT_FAMILY || !isPresenceCode(code) || !(rawJid instanceof String)) return null;
        String jid = (String) rawJid;
        if (jid.length() > 256 || !CONTACT_JID.matcher(jid).matches()) return null;
        // Non-null presence includes the host's "deny" response. It must not be
        // converted into a fabricated offline/last-seen timestamp.
        if (presence != null) return null;
        return new Event(jid, code == AVAILABLE);
    }
}
