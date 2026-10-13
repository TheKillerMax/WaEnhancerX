package com.waenhancer.xposed.features.privacy;

import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class TestRecipientReceiptAllowance {
    private static long checks;
    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        final String alice = "14155552671@s.whatsapp.net";
        final String bob = "14155552672@s.whatsapp.net";
        final String group = "14155552671@g.us";
        final String lid = "14155552671@lid";
        final RecipientReceiptAllowance a = new RecipientReceiptAllowance(120_000, 64);
        check(!a.isAllowed(alice, "M", 1), "unknown receipt cannot bypass");
        a.allow(alice, "M", 1);
        check(a.isAllowed(alice, "M", 1), "exact tuple allowed");
        check(!a.isAllowed(bob, "M", 1), "different phone cannot bypass");
        check(!a.isAllowed(lid, "M", 1), "same local part in LID must not bypass");
        check(!a.isAllowed(group, "M", 1), "same local part in group must not bypass");
        check(!a.isAllowed(alice, "N", 1), "second message in same chat denied");
        check(!a.isAllowed("jid="+alice, "M", 1), "embedded JID denied");
        check(!a.isAllowed(alice, null, 1), "missing message ID denied");
        check(a.isAllowed(alice, "M", 120001), "boundary TTL allowed");
        check(!a.isAllowed(alice, "M", 120002), "expired denied");
        a.allow(alice, "M", 200);
        a.revoke(alice, "M");
        check(!a.isAllowed(alice, "M", 201), "rollback revokes a staged grant");
        a.allow(alice, "", 1);
        a.allow(alice, "x\u0000y", 1);
        a.allow(alice, "X".repeat(1025), 1);
        a.allow(null, "M", 1);
        check(a.countForTests() == 0, "invalid grants do not grow cache");
        final Random r = new Random(0xB10E0D);
        final String[] recipients = {alice, bob, lid, group};
        final String[] ids = {"M", "N", "O", "P"};
        for (int i = 0; i < 100000; i++) {
            String jid = recipients[r.nextInt(recipients.length)];
            String id = ids[r.nextInt(ids.length)];
            long now = 1000L+i;
            a.allow(jid, id, now);
            check(a.isAllowed(jid, id, now), "just allowed tuple denied");
            check(!a.isAllowed(jid, "NEVER", now), "ungranted ID allowed");
            check(!a.isAllowed("jid="+jid, id, now), "prefix parser leaked recipient");
            check(a.countForTests() <= 64, "grant capacity exceeded");
        }
        final RecipientReceiptAllowance c = new RecipientReceiptAllowance(20000, 128);
        final CountDownLatch done = new CountDownLatch(8);
        final AtomicInteger failures = new AtomicInteger();
        for (int i = 0; i < 8; i++) {
            final int thread = i;
            new Thread(() -> {
                try {
                    for (int j = 0; j < 5000; j++) {
                        String jid = (thread*1000+j)+"@lid";
                        String id = "msg-" + thread + "-"+j;
                        c.allow(jid,id,j);
                        if(j%3==0)c.revoke(jid,id);
                        c.isAllowed(jid,id,j);
                    }
                } catch (Throwable t) { failures.incrementAndGet(); }
                finally { done.countDown(); }
            }).start();
        }
        done.await();
        check(failures.get() == 0, "concurrent operations threw");
        check(c.countForTests() <= 128, "concurrent cache unbounded");
        System.out.println("PASS: " + checks + " scoped read receipt assertions; 40,000 concurrent operations");
    }
}
