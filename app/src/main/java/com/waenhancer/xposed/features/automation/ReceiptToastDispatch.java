package com.waenhancer.xposed.features.automation;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;

/** Keeps receipt lookup and UI work bounded, with rollback of undelivered reservations. */
final class ReceiptToastDispatch {
    private static final ThreadLocal<Boolean> RETRYING = new ThreadLocal<>();
    interface Poster { boolean post(Runnable delivery); }
    interface Sink { boolean show(String message); }

    static void submit(ReceiptObservationPolicy.Observation event, ReceiptObservationPolicy.Seen seen,
                       Executor lookup, Poster ui, BooleanSupplier enabled, Supplier<String> text, Sink sink) {
        if (!enabled.getAsBoolean()) return;
        ReceiptObservationPolicy.Seen.Reservation reservation = seen.reserve(event);
        if (reservation == null) return;
        Pending task = new Pending(seen, reservation, ui, enabled, text, sink);
        boolean submitted = false;
        try {
            lookup.execute(task);
            submitted = true;
        } catch (RuntimeException | LinkageError rejected) {
            // Optional work can be retried if the executor cannot accept it.
        } finally {
            if (!submitted) task.cancel();
        }
    }

    /** The shared queue keeps its discard-oldest policy, releasing a receipt task if displaced. */
    static void discardOldest(Runnable next, ThreadPoolExecutor executor) {
        if (executor.isShutdown() || Boolean.TRUE.equals(RETRYING.get())) {
            cancel(next);
            return;
        }
        RETRYING.set(Boolean.TRUE);
        boolean submitted = false;
        try {
            cancel(executor.getQueue().poll());
            // execute also starts a worker if the old worker expired while rejecting.
            // A concurrent refill gets one retry; the reentry guard cancels it safely.
            executor.execute(next);
            submitted = true;
        } finally {
            RETRYING.remove();
            if (!submitted) cancel(next);
        }
    }

    private static void cancel(Runnable task) {
        if (task instanceof Pending) ((Pending) task).cancel();
    }

    private static final class Pending implements Runnable {
        final ReceiptObservationPolicy.Seen seen;
        final ReceiptObservationPolicy.Seen.Reservation reservation;
        final Poster ui;
        final BooleanSupplier enabled;
        final Supplier<String> text;
        final Sink sink;
        private volatile boolean cancelled;

        Pending(ReceiptObservationPolicy.Seen seen, ReceiptObservationPolicy.Seen.Reservation reservation,
                Poster ui, BooleanSupplier enabled, Supplier<String> text, Sink sink) {
            this.seen = seen; this.reservation = reservation; this.ui = ui;
            this.enabled = enabled; this.text = text; this.sink = sink;
        }

        void cancel() {
            // execute can throw after queue.offer (for example, worker creation fails).
            // That abandoned task may still run later alongside a legitimate retry.
            cancelled = true;
            seen.cancel(reservation);
        }

        @Override public void run() {
            boolean posted = false;
            try {
                if (cancelled || !enabled.getAsBoolean()) return;
                String message = text.get();
                if (cancelled || message == null || message.isEmpty() || !enabled.getAsBoolean()) return;
                posted = ui.post(() -> {
                    boolean shown = false;
                    try {
                        shown = !cancelled && enabled.getAsBoolean() && sink.show(message);
                    } catch (RuntimeException | LinkageError unavailable) {
                        // An optional notification must not interrupt the host UI.
                    } finally {
                        if (shown) seen.delivered(reservation); else cancel();
                    }
                });
            } catch (RuntimeException | LinkageError unavailable) {
                // Optional name/resource lookup; release the observation for a later retry.
            } finally {
                if (!posted) cancel();
            }
        }
    }

    private ReceiptToastDispatch() {}
}
