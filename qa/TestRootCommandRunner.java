package com.waenhancer.xposed.utils;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

/** Runs real unprivileged shell subprocesses to test the production bounded runner. */
public final class TestRootCommandRunner {
    private static int checks;
    private static void check(boolean result, String message) {
        checks++;
        if (!result) throw new AssertionError(message);
    }
    private static final RootCommandRunner.Starter SHELL =
            command -> new ProcessBuilder("sh", "-c", command)
                    .redirectErrorStream(true).start();

    public static void main(String[] args) throws Exception {
        check("ready".equals(RootCommandRunner.run("printf ready", 2_000L, SHELL)), "output capture");
        check("".equals(RootCommandRunner.run("true", 2_000L, SHELL)), "successful empty stdout");
        check("error".equals(RootCommandRunner.run("printf error >&2", 2_000L, SHELL)), "merged stderr");
        check(RootCommandRunner.run("false", 2_000L, SHELL) == null, "nonzero exit");
        check(RootCommandRunner.run("printf detail; exit 7", 2_000L, SHELL) == null, "exit failure with output");
        check(RootCommandRunner.run("", 2_000L, SHELL) == null, "blank command");
        check(RootCommandRunner.run(null, 2_000L, SHELL) == null, "null command");
        check(RootCommandRunner.run("true", 0L, SHELL) == null, "bad timeout");
        check(RootCommandRunner.run("true", 2_000L, null) == null, "null starter");
        check(RootCommandRunner.run("ignored", 2_000L, command -> { throw new IOException("su unavailable"); }) == null,
                "failure to start process");
        check(RootCommandRunner.run("ignored", 2_000L, command -> { throw new SecurityException("denied"); }) == null,
                "denied process start");
        // More than a pipe buffer, including one long line: the reader may store
        // 8 KiB at most, but must drain all data so the child finishes.
        String enormous = RootCommandRunner.run("yes Z | head -c 250000", 3_000L, SHELL);
        check(enormous != null && enormous.length() <= 8192 && enormous.length() >= 8000, "bounded output capture");
        check(enormous.startsWith("Z"), "first output chars kept");
        long start = System.nanoTime();
        check(RootCommandRunner.run("sleep 3", 200L, SHELL) == null, "timeout should fail");
        long elapsedMs = (System.nanoTime() - start) / 1_000_000L;
        check(elapsedMs < 1_800L, "timeout blocked for " + elapsedMs + "ms");

        AtomicBoolean interrupted = new AtomicBoolean();
        Thread waiter = new Thread(() -> {
            Thread.currentThread().interrupt();
            String result = RootCommandRunner.run("sleep 1", 2_000L, SHELL);
            interrupted.set(result == null && Thread.currentThread().isInterrupted());
        });
        waiter.start(); waiter.join(3_000L);
        check(!waiter.isAlive() && interrupted.get(), "preserve interrupted status");

        System.out.println("PASS: " + checks + " process exit, bounded IO, timeout and interruption checks");
    }
}
