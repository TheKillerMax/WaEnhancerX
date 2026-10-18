package com.waenhancer.xposed.views;

import java.lang.ref.WeakReference;
import java.lang.reflect.Field;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Executes the production executor with deterministic barriers, no timing sleeps. */
public final class TestStatusRowWorkQueue {
    static int checks;
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }
    static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("barrier timed out");
    }
    static final class Ui implements StatusRowWorkQueue.Dispatcher {
        final LinkedBlockingQueue<Runnable> messages = new LinkedBlockingQueue<>();
        final CountDownLatch posted = new CountDownLatch(1);
        boolean accept = true;
        public boolean post(Runnable value) {
            if (accept) messages.add(value);
            posted.countDown();
            return accept;
        }
        public void remove(Runnable value) { messages.remove(value); }
        void deliver() throws Exception {
            Runnable next = messages.poll(5, TimeUnit.SECONDS);
            if (next == null) throw new AssertionError("delivery timed out");
            next.run();
        }
    }
    public static void main(String[] args) throws Exception {
        String caller = Thread.currentThread().getName();
        AtomicInteger loads = new AtomicInteger(), deliveries = new AtomicInteger();
        AtomicReference<String> callbackThread = new AtomicReference<>();
        StatusRowWorkQueue.Target<String> target = (ticket, row) -> {
            deliveries.incrementAndGet(); callbackThread.set(Thread.currentThread().getName());
        };
        try (StatusRowWorkQueue queue = new StatusRowWorkQueue(1, 2)) {
            Ui ui = new Ui();
            CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
            StatusRowWorkQueue.Ticket<String> active = queue.submit(() -> {
                check(!Thread.currentThread().getName().equals(caller), "work is off caller");
                started.countDown(); await(release); return "active";
            }, target, ui);
            await(started);
            StatusRowWorkQueue.Ticket<String> removed = queue.submit(() -> {
                loads.incrementAndGet(); return "removed";
            }, target, ui);
            queue.submit(() -> { loads.incrementAndGet(); return "second"; }, target, ui);
            StatusRowWorkQueue.Ticket<String> rejected = queue.submit(() -> {
                throw new AssertionError("saturation ran on caller or entered queue");
            }, target, ui);
            check(rejected.isCancelled(), "bounded queue rejects excess");
            removed.cancel();
            StatusRowWorkQueue.Ticket<String> replacement = queue.submit(() -> {
                loads.incrementAndGet(); return "replacement";
            }, target, ui);
            check(!replacement.isCancelled(), "cancel removes queued work immediately");
            active.cancel(); release.countDown();
            ui.deliver(); ui.deliver();
            check(loads.get() == 2, "cancelled queued and active results are suppressed");
            check(deliveries.get() == 2, "only current jobs deliver");
            check(caller.equals(callbackThread.get()), "delivery uses supplied dispatcher");
        }
        try (StatusRowWorkQueue queue = new StatusRowWorkQueue(1, 2)) {
            Ui ui = new Ui();
            StatusRowWorkQueue.Ticket<String> ticket = queue.submit(() -> "posted", target, ui);
            await(ui.posted); ticket.cancel();
            check(ui.messages.isEmpty(), "cancellation removes posted UI callback");
            check(deliveries.get() == 2, "posted cancellation has no delivery");
        }
        try (StatusRowWorkQueue queue = new StatusRowWorkQueue(1, 2)) {
            Ui ui = new Ui();
            CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
            queue.submit(() -> { started.countDown(); await(release); return "barrier"; }, target, ui);
            await(started);
            AtomicInteger abandonedLoads = new AtomicInteger();
            StatusRowWorkQueue.Ticket<String> abandoned = queue.submit(() -> {
                abandonedLoads.incrementAndGet(); return "abandoned";
            }, target, ui);
            // Clear the exact production WeakReference, avoiding nondeterministic GC assertions.
            Field ref = abandoned.getClass().getDeclaredField("target"); ref.setAccessible(true);
            ((WeakReference<?>) ref.get(abandoned)).clear();
            queue.submit(() -> "tail", target, ui);
            release.countDown(); ui.deliver(); ui.deliver();
            check(abandonedLoads.get() == 0 && ui.messages.isEmpty(), "collected row neither loads nor delivers");
        }
        try (StatusRowWorkQueue queue = new StatusRowWorkQueue(1, 2)) {
            Ui ui = new Ui(); AtomicReference<String> result = new AtomicReference<>("unchanged");
            StatusRowWorkQueue.Target<String> errorTarget = (ticket, row) -> result.set(row);
            queue.submit(() -> { throw new IllegalStateException("fixture"); }, errorTarget, ui);
            ui.deliver(); check(result.get() == null, "loader failure returns empty result");
            Ui failedUi = new Ui(); failedUi.accept = false;
            StatusRowWorkQueue.Ticket<String> rejectedPost = queue.submit(() -> "discard", target, failedUi);
            await(failedUi.posted);
            // Wait for the synchronized post-result handling, not just the dispatcher signal.
            synchronized (rejectedPost) {
                Field field = rejectedPost.getClass().getDeclaredField("result"); field.setAccessible(true);
                check(field.get(rejectedPost) == null, "rejected UI post releases bitmap/result");
            }
        }
        for (int requested : new int[]{-1, 0, 1, 62, 186, 512, 10000}) {
            int targetSize = StatusThumbnailPolicy.targetSize(requested);
            check(targetSize >= 1 && targetSize <= 512, "target allocation bounded");
            for (int width : new int[]{1, 61, 4000, 48000, Integer.MAX_VALUE}) {
                for (int height : new int[]{1, 4000, Integer.MAX_VALUE}) {
                    int sample = StatusThumbnailPolicy.sampleSize(width, height, requested);
                    check(sample > 0 && (sample & (sample - 1)) == 0, "power-of-two sampling");
                    check((Math.max(width, height) + (long) sample - 1) / sample <= targetSize * 4,
                            "decoded longest edge bounded for portrait, panorama and huge header");
                }
            }
        }
        System.out.println("PASS: " + checks + " executor, cancellation, weak target and pixel-bound checks");
    }
}
