package com.waenhancer.xposed.features.automation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class TestNotificationState {
    private static void ok(boolean result, String message) { if (!result) throw new AssertionError(message); }
    public static void main(String[] args) throws Exception {
        ToastThrottle limiter = new ToastThrottle(1500, 2048);
        ok(limiter.shouldEmit("alice", 10000), "first event");
        ok(!limiter.shouldEmit("alice", 11499), "throttle within interval");
        ok(limiter.shouldEmit("alice", 11500), "interval boundary");
        ok(limiter.shouldEmit("alice", 50), "clock rollback");
        for (int i = 0; i < 12000; ++i) limiter.shouldEmit("jid-" + i, 12000);
        ok(limiter.trackedCountForTests() <= 2048, "bounded throttle cache");
        for (int i=0; i<20000; ++i) {
            PresenceStateStore.update("person-" + i + "@s.whatsapp.net", i%2==0);
        }
        ok(PresenceStateStore.stateCount() <= 2048, "bounded presence state");
        AtomicInteger hits = new AtomicInteger();
        PresenceStateStore.Listener crash = (jid, state) -> { throw new IllegalStateException("bad observer"); };
        PresenceStateStore.Listener brokenLinkage = (jid, state) -> { throw new NoClassDefFoundError("simulated missing WhatsApp class"); };
        PresenceStateStore.Listener good = (jid, state) -> hits.incrementAndGet();
        PresenceStateStore.addListener(crash);
        PresenceStateStore.addListener(brokenLinkage);
        PresenceStateStore.addListener(good);
        ok(PresenceStateStore.update("current@s.whatsapp.net", true), "change emits");
        ok(hits.get() == 1, "failed observer does not block next");
        ok(!PresenceStateStore.update("current@s.whatsapp.net", true), "duplicate suppressed");
        PresenceStateStore.removeListener(crash);
        PresenceStateStore.removeListener(brokenLinkage);
        PresenceStateStore.removeListener(good);
        CountDownLatch ready = new CountDownLatch(5);
        for (int t=0;t<5;t++) {
            final int id=t;
            new Thread(() -> {
                for (int i=0;i<2000;i++) limiter.shouldEmit("concurrent-" + id + "-" + i, i);
                ready.countDown();
            }).start();
        }
        ready.await();
        ok(limiter.trackedCountForTests() <= 2048, "concurrent bounded throttle");
        // Concurrent presence updates must remain bounded and survive access-order LRU reads.
        CountDownLatch presenceReady = new CountDownLatch(6);
        AtomicReference<Throwable> presenceFailure = new AtomicReference<>();
        for (int t = 0; t < 6; t++) {
            final int worker = t;
            new Thread(() -> {
                try {
                    for (int i = 0; i < 2000; i++) {
                        String jid = "parallel-" + worker + "-" + i + "@s.whatsapp.net";
                        PresenceStateStore.update(jid, true);
                        PresenceStateStore.get(jid);
                    }
                } catch (Throwable failure) {
                    presenceFailure.compareAndSet(null, failure);
                } finally {
                    presenceReady.countDown();
                }
            }).start();
        }
        ok(presenceReady.await(30, TimeUnit.SECONDS), "concurrent presence workers completed");
        ok(presenceFailure.get() == null, "concurrent presence updates and reads");
        ok(PresenceStateStore.stateCount() <= 2048, "concurrent presence cache stays bounded");
        System.out.println("PASS: toast throttle and presence state bounds, concurrency, listeners");
    }
}
