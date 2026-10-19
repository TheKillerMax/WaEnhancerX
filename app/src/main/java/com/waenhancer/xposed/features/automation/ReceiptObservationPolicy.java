package com.waenhancer.xposed.features.automation;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

/** An observed incoming read receipt is not a claim about a host database commit. */
final class ReceiptObservationPolicy {
    static final int READ_RECEIPT = 13;
    static final int MAX_BATCH = 300;
    private static final Pattern USER = Pattern.compile("[0-9]+@(s\\.whatsapp\\.net|whatsapp\\.net|lid)");
    private static final Pattern GROUP = Pattern.compile("[0-9]+(?:-[0-9]+)?@g\\.us");

    enum Kind { MESSAGE, STATUS }

    static final class Observation {
        final Kind kind;
        final String chat;
        final String messageId;
        final String viewer;

        private Observation(Kind kind, String chat, String messageId, String viewer) {
            this.kind = kind;
            this.chat = chat;
            this.messageId = messageId;
            this.viewer = viewer;
        }

        @Override public boolean equals(Object other) {
            if (!(other instanceof Observation)) return false;
            Observation that = (Observation) other;
            return kind == that.kind && chat.equals(that.chat)
                    && messageId.equals(that.messageId) && viewer.equals(that.viewer);
        }

        @Override public int hashCode() { return Objects.hash(kind, chat, messageId, viewer); }
    }

    static Observation capture(Kind kind, int type, long timestamp, boolean fromMe,
                               String chat, String messageId, String viewer) {
        if (kind == null || type != READ_RECEIPT || timestamp <= 0L || !fromMe
                || !identifier(messageId, 256) || !identifier(chat, 160)
                || !identifier(viewer, 160) || !USER.matcher(viewer).matches()) return null;
        boolean group = GROUP.matcher(chat).matches();
        boolean supportedChat = kind == Kind.MESSAGE
                ? group || USER.matcher(chat).matches()
                : group || "status@broadcast".equals(chat);
        if (!supportedChat) return null;
        return new Observation(kind, chat, messageId, viewer);
    }

    private static boolean identifier(String value, int maxLength) {
        if (value == null || value.isEmpty() || value.length() > maxLength) return false;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isWhitespace(c) || Character.isISOControl(c)) return false;
        }
        return true;
    }

    /** Process-local bounded identity history; neither timestamps nor switches change identity. */
    static final class Seen {
        private final int capacity;
        private final int pendingCapacity;
        private final Map<Observation, Boolean> recent = new LinkedHashMap<>();
        private final Map<Observation, Reservation> pending = new LinkedHashMap<>();

        Seen(int capacity, int pendingCapacity) {
            if (capacity < 1 || pendingCapacity < 1) throw new IllegalArgumentException("capacity");
            this.capacity = capacity;
            this.pendingCapacity = pendingCapacity;
        }

        static final class Reservation {
            final Observation event;
            private Reservation(Observation event) { this.event = event; }
        }

        synchronized Reservation reserve(Observation event) {
            if (event == null || recent.containsKey(event) || pending.containsKey(event)
                    || pending.size() >= pendingCapacity) return null;
            Reservation reservation = new Reservation(event);
            pending.put(event, reservation);
            return reservation;
        }

        synchronized void delivered(Reservation reservation) {
            if (reservation == null || pending.get(reservation.event) != reservation) return;
            pending.remove(reservation.event);
            recent.put(reservation.event, Boolean.TRUE);
            if (recent.size() > capacity) {
                Iterator<Observation> keys = recent.keySet().iterator();
                keys.next();
                keys.remove();
            }
        }

        synchronized void cancel(Reservation reservation) {
            if (reservation != null && pending.get(reservation.event) == reservation)
                pending.remove(reservation.event);
        }

        synchronized int sizeForTests() { return recent.size(); }
        synchronized int pendingForTests() { return pending.size(); }
    }

    private ReceiptObservationPolicy() {}
}
