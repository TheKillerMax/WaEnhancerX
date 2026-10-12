package com.waenhancer.xposed.features.automation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

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
        ok(PresenceStateStore.trackedCountForTests() <= 4096, "bounded presence state");
        AtomicInteger hits = new AtomicInteger();
        PresenceStateStore.Listener crash = (jid, state) -> { throw new IllegalStateException("bad observer"); };
        PresenceStateStore.Listener good = (jid, state) -> hits.incrementAndGet();
        PresenceStateStore.addListener(crash);
        PresenceStateStore.addListener(good);
        ok(PresenceStateStore.update("current@s.whatsapp.net", true), "change emits");
        ok(hits.get() == 1, "failed observer does not block next");
        ok(!PresenceStateStore.update("current@s.whatsapp.net", true), "duplicate suppressed");
        PresenceStateStore.removeListener(crash);
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
        System.out.println("PASS: toast throttle and presence state bounds, concurrency, listeners");
    }
}
