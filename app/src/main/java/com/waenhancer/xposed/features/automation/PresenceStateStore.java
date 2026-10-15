package com.waenhancer.xposed.features.automation;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/** Process-local presence state shared by the receiver hook and visible conversation rows. */
public final class PresenceStateStore {
    private static final int MAX_STATES = 2048;
    private static long nextRevision;
    public interface Listener { void onPresenceChanged(String jid, State state); }

    public static final class State {
        public final boolean online;
        public final long changedAtMillis;
        public final long revision;
        private State(boolean online, long changedAtMillis, long revision) {
            this.online = online;
            this.changedAtMillis = changedAtMillis;
            this.revision = revision;
        }
    }

    private static final Map<String, State> STATES = Collections.synchronizedMap(
            new LinkedHashMap<String, State>(256, 0.75f, true) {
                @Override protected boolean removeEldestEntry(Map.Entry<String, State> eldest) {
                    return size() > MAX_STATES;
                }
            });
    private static final Set<Listener> LISTENERS = new CopyOnWriteArraySet<>();

    private PresenceStateStore() {}

    public static State get(String jid) { return jid == null ? null : STATES.get(normalize(jid)); }
    /** Atomic read of explicitly equivalent identities; never guesses namespace aliases. */
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
        String key = normalize(jid);
        if (key.isEmpty() || key.contains("@g.us")) return false;
        State state;
        boolean transition;
        synchronized (STATES) {
            State old = STATES.get(key);
            transition = old == null || old.online != online;
            long changedAt = transition ? System.currentTimeMillis() : old.changedAtMillis;
            state = new State(online, changedAt, ++nextRevision);
            STATES.put(key, state);
        }
        // Listeners repaint observations; the return value still suppresses duplicate toasts.
        // Sequence numbers, rather than wall-clock timestamps, order queued/alias observations.
        for (Listener listener : LISTENERS) {
            try { listener.onPresenceChanged(key, state); }
            catch (RuntimeException | LinkageError ignored) { /* Isolate incompatible listeners. */ }
        }
        return transition;
    }

    public static String normalize(String jid) {
        if (jid == null) return "";
        String value = jid.trim();
        int slash = value.indexOf('/');
        if (slash > 0) value = value.substring(0, slash);
        return value;
    }
}
