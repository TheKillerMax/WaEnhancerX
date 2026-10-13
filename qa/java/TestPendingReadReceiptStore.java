package com.waenhancer.xposed.features.privacy;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class TestPendingReadReceiptStore {
    private static int checks;
    private static void check(boolean ok, String message) {
        checks++;
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        PendingReadReceiptStore<String> store = new PendingReadReceiptStore<>(3, 2);
        store.add("a@s.whatsapp.net", "a1");
        store.add("a@lid", "lid1");
        check(store.drain("unknown@s.whatsapp.net").isEmpty(), "unrelated chat cannot drain");
        check(store.drain("a@g.us").isEmpty(), "same user part does not cross domain");
        check(store.pendingCount("a@lid") == 1, "LID recipient stays queued");
        check(store.drain(null).isEmpty(), "unknown recipient fails closed");
        check(store.drain("a@s.whatsapp.net").equals(List.of("a1")), "exact match releases only exact recipient");
        check(store.drain("a@s.whatsapp.net").isEmpty(), "drain is one-time");
        check(store.drain("a@lid").equals(List.of("lid1")), "LID queue unaffected");
        store.add("a@g.us", "1");store.add("a@g.us", "2");store.add("a@g.us", "3");
        check(store.drain("a@g.us").equals(List.of("2","3")), "oldest job evicted within chat");
        store.add("first@lid", "old");store.add("second@lid", "newer");
        store.add("third@lid", "newest");store.add("fourth@lid", "recent");
        check(store.recipientCount() == 3, "number of chats bounded");
        check(store.drain("first@lid").isEmpty(), "eldest chat evicted");
        check(store.drain("fourth@lid").equals(List.of("recent")), "recent chat retained");
        check(store.drain("second@lid").equals(List.of("newer")), "second recent retained");
        check(store.drain("third@lid").equals(List.of("newest")), "third recent retained");
        boolean invalid = false;
        try {new PendingReadReceiptStore<>(0, 1);} catch (IllegalArgumentException e) {invalid = true;}
        check(invalid, "invalid max chat rejected");
        invalid = false;
        try {store.add(null, "job");} catch (NullPointerException e) {invalid = true;}
        check(invalid, "null key rejected");
        check(store.recipientCount() == 0, "test cleanup");
        PendingReadReceiptStore<Integer> concurrent = new PendingReadReceiptStore<>(48, 32);
        int threads = 6;
        CountDownLatch latch = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger();
        for(int t=0;t<threads;t++) {
            final int worker=t;
            new Thread(() -> {
                try {
                    String jid = "thread-"+worker+"@s.whatsapp.net";
                    for(int n=0;n<1000;n++) concurrent.add(jid,n);
                    if(concurrent.pendingCount(jid)!=32) failures.incrementAndGet();
                } catch (Throwable e) {failures.incrementAndGet();}
                finally {latch.countDown();}
            }).start();
        }
        latch.await();
        check(failures.get()==0,"concurrent writers succeed");
        check(concurrent.recipientCount()<=48,"concurrent capacity bounded");
        check(concurrent.drain("thread-1@s.whatsapp.net").size()==32,"concurrent per-chat bounded");
        System.out.println("PASS: "+checks+" direct routing/capacity checks and 6,000 concurrent insertions");
    }
}
