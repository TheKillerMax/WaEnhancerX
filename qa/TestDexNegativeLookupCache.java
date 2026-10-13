package com.waenhancer.xposed.core.devkit;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/** Pure JDK tests for time-bounded, size-bounded, typed negative lookups. */
public final class TestDexNegativeLookupCache {
    private static int checks;
    private static void check(boolean condition, String why) {
        checks++;
        if (!condition) throw new AssertionError(why);
    }

    public static void main(String[] args) throws Exception {
        DexNegativeLookupCache cache = new DexNegativeLookupCache(60_000L, 2048);
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 500L), "first attempt");
        cache.recordFailure(DexNegativeLookupCache.Kind.METHOD, "f", 500L);
        check(cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 500L), "cooldown immediate");
        check(cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 60_499L), "cooldown boundary -1");
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 60_500L), "allow retry at exactly 60s");
        check(cache.sizeForTests() == 0, "expired entries removed on access");
        cache.recordFailure(DexNegativeLookupCache.Kind.METHOD, "f", 70000L);
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "f", 70001L), "different lookup kinds must not block each other");
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.FIELD, "f", 70001L), "field kind separate");
        check(cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 70001L), "method still cooling down");
        cache.recordFailure(DexNegativeLookupCache.Kind.CLASS, "f", 71000L);
        cache.clearFailure(DexNegativeLookupCache.Kind.METHOD, "f");
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, "f", 71001L), "success clears own kind");
        check(cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "f", 71001L), "does not clear another kind");
        // A monotonic system clock should never go backwards. If it does, don't poison retries.
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "f", 100L), "clock rollback resets negative");
        for (int i = 0; i < 10000; i++) cache.recordFailure(DexNegativeLookupCache.Kind.CLASS, "missing-" + i, 90000L);
        check(cache.sizeForTests() == 2048, "capacity limit");
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "missing-0", 90001L), "oldest entry evicted");
        check(cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "missing-9999", 90001L), "recent entry retained");
        cache.clear();
        check(cache.sizeForTests() == 0, "clear removes negative entries");
        check(!cache.shouldSkip(DexNegativeLookupCache.Kind.CLASS, "missing-9999", 90001L), "clear permits immediate retry");
        boolean rejected = false;
        try { new DexNegativeLookupCache(0L, 1); } catch (IllegalArgumentException ok) { rejected = true; }
        check(rejected, "nonpositive retry delay rejected");
        rejected = false;
        try { new DexNegativeLookupCache(1L, 0); } catch (IllegalArgumentException ok) { rejected = true; }
        check(rejected, "nonpositive capacity rejected");
        rejected = false;
        try { cache.recordFailure(null, "f", 0L); } catch (NullPointerException ok) { rejected = true; }
        check(rejected, "null kind rejected");
        rejected = false;
        try { cache.recordFailure(DexNegativeLookupCache.Kind.METHOD, null, 0L); } catch (NullPointerException ok) { rejected = true; }
        check(rejected, "null key rejected");

        // Heavy concurrent writes/reads must remain bounded, coherent, and exception-free.
        final int threads = 8;
        CountDownLatch latch = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger();
        for (int i = 0; i < threads; i++) {
            final int id = i;
            new Thread(() -> {
                try {
                    for (int j = 0; j < 4000; j++) {
                        String key = "worker-" + id + ":" + (j % 64);
                        cache.recordFailure(DexNegativeLookupCache.Kind.METHOD, key, 100000L);
                        if (!cache.shouldSkip(DexNegativeLookupCache.Kind.METHOD, key, 100000L)) failures.incrementAndGet();
                    }
                } catch (Throwable t) { failures.incrementAndGet(); }
                finally { latch.countDown(); }
            }).start();
        }
        latch.await();
        check(failures.get() == 0, "concurrent operations completed");
        check(cache.sizeForTests() <= 2048, "concurrent capacity bound");
        // Unique concurrent keys may legitimately be evicted before a subsequent read;
        // only the global capacity (not instant retention of every key) is guaranteed.
        CountDownLatch uniqueDone = new CountDownLatch(threads);
        for (int i = 0; i < threads; i++) {
            final int id = i;
            new Thread(() -> {
                try {
                    for (int j = 0; j < 3000; j++) {
                        cache.recordFailure(DexNegativeLookupCache.Kind.FIELD,
                                "unique-" + id + ":" + j, 100000L);
                    }
                } catch (Throwable t) { failures.incrementAndGet(); }
                finally { uniqueDone.countDown(); }
            }).start();
        }
        uniqueDone.await();
        check(failures.get() == 0, "concurrent unique-key operations completed");
        check(cache.sizeForTests() <= 2048, "concurrent eviction capacity bound");
        System.out.println("PASS: " + checks + " direct cooldown assertions plus 32,000 concurrent lookup iterations");
    }
}
