package com.waenhancer.xposed.core;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * Serial, bounded delivery of optional injection diagnostics. A slow Binder call owns at most
 * one worker; each kind retains only its newest pending task. Hook installation and preference
 * writes must never use this lossy queue.
 */
public final class RuntimeReportDispatcher {
    public enum Kind { PACKAGE, HEALTH, HOOKS, UPDATE_CHECK }

    private final Executor executor;
    private final Consumer<Throwable> failureReporter;
    private final Map<Kind, Runnable> pending = new LinkedHashMap<>();
    private boolean released;
    private boolean draining;

    public RuntimeReportDispatcher(Consumer<Throwable> failureReporter) {
        this(failureReporter, true);
    }

    public RuntimeReportDispatcher(Consumer<Throwable> failureReporter, boolean released) {
        this(Executors.newSingleThreadExecutor(task -> {
            Thread worker = new Thread(task, "WAEX-Report");
            worker.setDaemon(true);
            worker.setPriority(Thread.MIN_PRIORITY);
            return worker;
        }), failureReporter, released);
    }

    RuntimeReportDispatcher(Executor executor, Consumer<Throwable> failureReporter) {
        this(executor, failureReporter, true);
    }

    RuntimeReportDispatcher(Executor executor, Consumer<Throwable> failureReporter, boolean released) {
        this.executor = Objects.requireNonNull(executor);
        this.failureReporter = Objects.requireNonNull(failureReporter);
        this.released = released;
    }

    public void submitLatest(Kind kind, Runnable task) {
        Objects.requireNonNull(kind);
        Objects.requireNonNull(task);
        synchronized (pending) {
            // HEALTH replacement moves READY after a previously queued catalogue. HOOKS
            // replacement keeps that reserved position while updating its payload, so a lazy
            // catalogue refresh cannot move an undelivered inventory behind pending READY.
            if (kind != Kind.HOOKS) {
                pending.remove(kind);
            }
            pending.put(kind, task);
            scheduleLocked();
        }
    }

    /** Releases startup reports once the first screen is visible or the fallback fires. */
    public void release() {
        synchronized (pending) {
            released = true;
            scheduleLocked();
        }
    }

    private void scheduleLocked() {
        if (!released || draining || pending.isEmpty()) return;
        draining = true;
        try {
            executor.execute(this::drain);
        } catch (RuntimeException rejected) {
            draining = false;
            pending.clear();
            reportFailure(rejected);
        }
    }

    private void drain() {
        boolean completed = false;
        try {
            while (true) {
                Runnable task;
                synchronized (pending) {
                    if (pending.isEmpty()) {
                        draining = false;
                        completed = true;
                        return;
                    }
                    Kind first = pending.keySet().iterator().next();
                    task = pending.remove(first);
                }
                try {
                    task.run();
                } catch (Throwable failure) {
                    if (failure instanceof VirtualMachineError) throw (VirtualMachineError) failure;
                    if (failure instanceof ThreadDeath) throw (ThreadDeath) failure;
                    reportFailure(failure);
                }
            }
        } finally {
            if (!completed) {
                synchronized (pending) { draining = false; }
            }
        }
    }

    private void reportFailure(Throwable failure) {
        try {
            failureReporter.accept(failure);
        } catch (Throwable unavailable) {
            if (unavailable instanceof VirtualMachineError) throw (VirtualMachineError) unavailable;
            if (unavailable instanceof ThreadDeath) throw (ThreadDeath) unavailable;
        }
    }
}
