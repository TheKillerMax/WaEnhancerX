package com.waenhancer.xposed.utils;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Runs root shell commands with bounded wait and captured output (but always drains stdout). */
public final class RootCommandRunner {
    /** Shared bounded root execution for the manager and injected utility callers. */
    public static String run(String command, long timeoutMillis) {
        return run(command, timeoutMillis,
                value -> new ProcessBuilder("su", "-c", value).redirectErrorStream(true).start());
    }

    private static final int MAX_CAPTURE_CHARS = 8192;
    private static final int READ_CHUNK = 1024;

    /** Config readers require the complete output, never a silently truncated document. */
    public static String runBounded(String command, long timeoutMillis, int captureLimit) {
        return runBounded(command, timeoutMillis, captureLimit,
                value -> new ProcessBuilder("su", "-c", value).redirectErrorStream(true).start());
    }

    static String runBounded(String command, long timeoutMillis, int captureLimit, Starter starter) {
        if (captureLimit < 1 || captureLimit > 1024 * 1024) return null;
        return run(command, timeoutMillis, captureLimit, true, starter);
    }

    @FunctionalInterface
    interface Starter { Process start(String command) throws IOException; }

    private RootCommandRunner() {}

    /** A null result means startup, exit, timeout or stream processing failed. Empty output can be success. */
    static String run(String command, long timeoutMillis, Starter starter) {
        return run(command, timeoutMillis, MAX_CAPTURE_CHARS, false, starter);
    }

    private static String run(String command, long timeoutMillis, int captureLimit,
                              boolean requireComplete, Starter starter) {
        if (command == null || command.trim().isEmpty() || timeoutMillis <= 0 || starter == null) return null;
        Process process = null;
        Thread drain = null;
        StringBuilder output = new StringBuilder(Math.min(captureLimit, MAX_CAPTURE_CHARS));
        AtomicBoolean incomplete = new AtomicBoolean();
        try {
            process = starter.start(command);
            final Process currentProcess = process;
            drain = new Thread(() -> {
                try (Reader reader = new InputStreamReader(
                        currentProcess.getInputStream(), StandardCharsets.UTF_8)) {
                    char[] chunk = new char[READ_CHUNK];
                    int count;
                    while ((count = reader.read(chunk)) != -1) {
                        synchronized (output) {
                            int room = captureLimit - output.length();
                            if (count > room) incomplete.set(true);
                            if (room > 0) output.append(chunk, 0, Math.min(room, count));
                        }
                        // Keep draining even after the capture is full so the process
                        // never blocks on a full OS pipe.
                    }
                } catch (IOException ignored) {
                    incomplete.set(true);
                    // Process termination can close the stream while it is being read.
                }
            }, "WAEX-root-stdout");
            drain.setDaemon(true);
            drain.start();
            // Poll exitValue rather than using Process.waitFor(timeout, unit),
            // which is not reliably available on the application's minSdk 24.
            long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
            boolean completed = false;
            while (System.nanoTime() < deadline) {
                try {
                    process.exitValue();
                    completed = true;
                    break;
                } catch (IllegalThreadStateException stillRunning) {
                    long remainingNanos = deadline - System.nanoTime();
                    if (remainingNanos <= 0) break;
                    long sleepMillis = Math.min(25L,
                            Math.max(1L, TimeUnit.NANOSECONDS.toMillis(remainingNanos)));
                    Thread.sleep(sleepMillis);
                }
            }
            if (!completed) {
                terminate(process);
                return null;
            }
            if (drain.isAlive()) drain.join(250L);
            if (process.exitValue() != 0) return null;
            if (requireComplete && (drain.isAlive() || incomplete.get())) return null;
            synchronized (output) { return output.toString().trim(); }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return null;
        } catch (IOException | RuntimeException failure) {
            return null;
        } finally {
            if (process != null) terminate(process);
            if (drain != null && drain.isAlive()) drain.interrupt();
        }
    }

    private static void terminate(Process process) {
        try { process.destroy(); } catch (RuntimeException ignored) {}
        // Reflection preserves Android API 24 support where destroyForcibly()
        // may not be linked, while using it on runtimes that provide it.
        try {
            Process.class.getMethod("destroyForcibly").invoke(process);
        } catch (ReflectiveOperationException | SecurityException ignored) {}
    }
}
