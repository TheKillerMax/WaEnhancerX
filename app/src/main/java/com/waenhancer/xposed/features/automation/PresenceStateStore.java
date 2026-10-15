package com.waenhancer.xposed.features.automation;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/** Process-local observations, not authoritative server last-seen information. */
public final class PresenceStateStore {
    private static final int MAX_STATES = 2048;
    private static long nextRevision;
    /** An empty jid is a global invalidation signal; listeners must reread their state. */
    public interface Listener { void onPresenceChanged(String jid, State state); }

    public static final class State {
        public final boolean online;
        public final boolean known;
        public final long changedAtMillis;
        public final long revision;
        public final long transitionRevision;
        private State(boolean online, boolean known, long changedAtMillis,
                      long revision, long transitionRevision) {
            this.online = online;
            this.known = known;
            this.changedAtMillis = changedAtMillis;
            this.revision = revision;
            this.transitionRevision = transitionRevision;
        }
    }

    // Retain by observation order, not UI access order. Otherwise reading an old
    // alias can keep it alive after its newer invalidation tombstone is evicted.
    private static final Map<String, State> STATES = Collections.synchronizedMap(
            new LinkedHashMap<String, State>(256, 0.75f, false) {
                @Override protected boolean removeEldestEntry(Map.Entry<String, State> eldest) {
                    return size() > MAX_STATES;
                }
            });
    private static final Set<Listener> LISTENERS = new CopyOnWriteArraySet<>();

    private PresenceStateStore() {}

    public static State get(String jid) { return jid == null ? null : STATES.get(normalize(jid)); }
    /** Atomic read of explicitly equivalent identities, including unknown tombstones. */
    public static State getLatest(Iterable<String> identities) {
        if (identities == null) return null;
        synchronized (STATES) {
            State latest = null;
            for (String identity : identities) {
                State candidate = identity == null ? null : STATES.get(normalize(identity));
                if (candidate != null && (latest == null || candidate.revision > latest.revision)) {
                    latest = candidate;
                }
            }
            return latest;
        }
    }

    static int stateCount() { return STATES.size(); }
    public static void addListener(Listener listener) { if (listener != null) LISTENERS.add(listener); }
    public static void removeListener(Listener listener) { LISTENERS.remove(listener); }

    public static boolean update(String jid, boolean online) {
        return updateAndGetTransition(jid, online) != 0L;
    }

    /** Returns this exact observation's transition ID, or zero for a repeat/invalid input.
     * Do not reread a possibly newer observation after callbacks have run. */
    public static long updateAndGetTransition(String jid, boolean online) {
        return record(jid, true, online);
    }

    /** Denial is unknown, not offline. A tombstone masks older explicitly linked aliases. */
    public static void invalidate(String jid) { record(jid, false, false); }

    /** Only call for a verified transport lifecycle event; never synthesize contact states. */
    public static void invalidateAll() {
        State signal;
        synchronized (STATES) {
            if (STATES.isEmpty()) return;
            STATES.clear();
            long revision = ++nextRevision;
            signal = new State(false, false, 0L, revision, revision);
        }
        notifyListeners("", signal);
    }

    public static boolean isCurrentOnline(String jid, long transitionRevision) {
        State state = get(jid);
        return state != null && state.known && state.online
                && state.transitionRevision == transitionRevision;
    }

    private static long record(String jid, boolean known, boolean online) {
        String key = normalize(jid);
        if (key.isEmpty() || key.contains("@g.us")) return 0L;
        State state;
        boolean transition;
        synchronized (STATES) {
            State old = STATES.get(key);
            transition = known && (old == null || !old.known || old.online != online);
            long revision = ++nextRevision;
            long changedAt = !known ? 0L : transition ? System.currentTimeMillis() : old.changedAtMillis;
            long transitionId = !known || transition ? revision : old.transitionRevision;
            state = new State(online, known, changedAt, revision, transitionId);
            STATES.remove(key);
            STATES.put(key, state);
        }
        // Repeat observations refresh rows but do not emit duplicate toast transitions.
        notifyListeners(key, state);
        return transition ? state.transitionRevision : 0L;
    }

    private static void notifyListeners(String key, State state) {
        for (Listener listener : LISTENERS) {
            try { listener.onPresenceChanged(key, state); }
            catch (RuntimeException | LinkageError ignored) { /* Isolate incompatible listeners. */ }
        }
    }

    public static String normalize(String jid) {
        if (jid == null) return "";
        String value = jid.trim();
        int slash = value.indexOf('/');
        if (slash > 0) value = value.substring(0, slash);
        return value;
    }
}
