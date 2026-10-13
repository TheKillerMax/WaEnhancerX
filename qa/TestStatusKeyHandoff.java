package com.waenhancer.xposed.features.privacy;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class TestStatusKeyHandoff {
    private static int checks;
    private static void check(boolean yes, String label) {
        checks++;
        if (!yes) throw new AssertionError(label);
    }
    public static void main(String[] args) throws InterruptedException {
        check(StatusKeyHandoff.consume() == null, "unpopulated cache must be empty");
        StatusKeyHandoff.record("status-A");
        check("status-A".equals(StatusKeyHandoff.consume()), "first status handed off");
        check(StatusKeyHandoff.consume() == null, "consumed status must not be reused");
        StatusKeyHandoff.record("status-A");
        StatusKeyHandoff.record("status-B");
        check("status-B".equals(StatusKeyHandoff.consume()), "latest event replaces old one");
        StatusKeyHandoff.record("status-C");
        StatusKeyHandoff.record(null);
        check(StatusKeyHandoff.consume() == null, "null invalidates previous observation");
        StatusKeyHandoff.record("status-D");
        StatusKeyHandoff.record("");
        check(StatusKeyHandoff.consume() == null, "empty ID must invalidate previous observation");
        final int threads = 8;
        final CountDownLatch ready = new CountDownLatch(threads);
        final CountDownLatch start = new CountDownLatch(1);
        final CountDownLatch done = new CountDownLatch(threads);
        final AtomicInteger failures = new AtomicInteger();
        for (int i = 0; i < threads; i++) {
            final int idx = i;
            Thread worker = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    for (int j = 0; j < 25000; j++) {
                        String key = idx + ":" + j;
                        StatusKeyHandoff.record(key);
                        if (!key.equals(StatusKeyHandoff.consume())) failures.incrementAndGet();
                        if (StatusKeyHandoff.consume() != null) failures.incrementAndGet();
                    }
                } catch (Throwable ex) { failures.incrementAndGet(); }
                finally { done.countDown(); }
            }, "status-test-" + i);
            worker.start();
        }
        ready.await(); start.countDown(); done.await();
        check(failures.get() == 0, "thread leakage / repeated reads detected");
        check(StatusKeyHandoff.consume() == null, "main thread unaffected");
        System.out.println("PASS: " + checks + " direct and 200,000 thread-isolated handoffs");
    }
}
