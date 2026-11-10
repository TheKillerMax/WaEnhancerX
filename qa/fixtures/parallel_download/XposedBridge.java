package de.robv.android.xposed;

/** Minimal log double; the real stream is compiled and exercised unchanged. */
public final class XposedBridge {
    private XposedBridge() {}
    public static final java.util.List<String> messages = new java.util.concurrent.CopyOnWriteArrayList<>();
    public static void log(String message) { messages.add(message); }
}
