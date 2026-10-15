package com.waenhancer.xposed.features.automation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/** Exercises production TaskerMessagePolicy without Android or Xposed dependencies. */
public final class TestTaskerMessagePolicy {
    private static int checks;
    private static void expect(boolean actual, String description) {
        checks++;
        if (!actual) throw new AssertionError(description);
    }
    private static TaskerMessagePolicy.PreparedMessage good(String input, String text, String phone) {
        TaskerMessagePolicy.PreparedMessage result = TaskerMessagePolicy.prepare(input, text);
        expect(result != null, "valid input rejected: " + input);
        expect(phone.equals(result.phone), "wrong normalized number: " + input);
        expect(text.equals(result.text), "text was mutated: " + input);
        return result;
    }
    private static void bad(String input, String text) {
        expect(TaskerMessagePolicy.prepare(input, text) == null, "invalid recipient/content accepted: " + input);
    }
    public static void main(String[] args) throws Exception {
        good("+1 (415) 555-2671", "Hola mundo", "14155552671");
        good("+34 612-34-56-78", "α & β?= 🟢", "34612345678");
        good("14155552671@s.whatsapp.net", "A\nB", "14155552671");
        good("14155552671@c.us", "older JID", "14155552671");
        good("1234567", " hi ", "1234567");
        good("123456789012345", "valid maximum", "123456789012345");
        good("  +1 (415) 555-2671  ", "space", "14155552671");
        good("+44.7700.900-123", "unicode 🍣", "447700900123");
        good("14155552671", "\nBody\n", "14155552671");
        good("14155552671", "A".repeat(TaskerMessagePolicy.MAX_MESSAGE_CHARS), "14155552671");
        bad(null, "text"); bad("14155552671", null); bad("", "text");
        bad("14155552671", "   \t\n"); bad("14155552671", "");
        bad("14155552671", "A".repeat(TaskerMessagePolicy.MAX_MESSAGE_CHARS + 1));
        bad("14155552671", "\0payload");
        bad("+123456", "text"); bad("+1234567890123456", "text");
        bad("+", "text"); bad("+1-", "text");
        bad("++14155552671", "text"); bad("141+55552671", "text");
        bad("abc14155552671", "text"); bad("14155552671x", "text");
        bad("14155552671&text=ATTACK", "text");
        bad("14155552671?foo=bar", "text");
        bad("14155552671@s.whatsapp.net.evil", "text");
        bad("14155552671@lid", "text");
        bad("14155552671@c.us.evil", "text");
        bad("141 555@s.whatsapp.net", "text");
        bad("+14155552671@s.whatsapp.net", "text");
        bad("１４１５５５５２６７１", "text");
        bad("14155552671\r\n", "text");
        bad("(1)".repeat(30), "text");
        bad("1".repeat(TaskerMessagePolicy.MAX_PHONE_INPUT_CHARS + 1), "text");
        bad("14155552671@example.com", "text");
        for (int len = 0; len <= 22; len++) {
            String number = "1".repeat(len);
            expect((TaskerMessagePolicy.prepare(number, "hi") != null) == (len >= 7 && len <= 15),
                    "incorrect E.164 length boundary: " + len);
        }
        // Deterministic invalid phone fuzz: reject URI delimiter, Unicode and letters.
        String[] unwanted = {"@", "/", "&", "?", "#", "=", "\\", "!", ";", "a", "\u0661", "\n", "\r", "%"};
        for (int i = 0; i < 10000; i++) {
            String input = "1415" + unwanted[i % unwanted.length] + "5552671";
            expect(TaskerMessagePolicy.prepare(input, "body") == null,
                   "invalid separator unexpectedly accepted: iteration " + i);
        }

        TaskerMessagePolicy.LaunchGate gate = new TaskerMessagePolicy.LaunchGate(1500L);
        expect(!gate.tryAcquire(-1), "negative clock accepted");
        expect(gate.tryAcquire(0), "first launch rejected");
        expect(!gate.tryAcquire(1499), "rapid duplicate launch accepted");
        expect(gate.tryAcquire(1500), "boundary launch rejected");
        expect(!gate.tryAcquire(1500), "same timestamp duplicated");
        expect(gate.tryAcquire(10), "clock rollback must reset");
        expect(!gate.tryAcquire(11), "duplicate after rollback accepted");
        expect(gate.tryAcquire(1510), "launch gate never reopened");
        boolean rejected = false;
        try { new TaskerMessagePolicy.LaunchGate(0); } catch (IllegalArgumentException expected) { rejected = true; }
        expect(rejected, "zero throttle interval allowed");
        // Concurrent callers must not all pass the gate.
        TaskerMessagePolicy.LaunchGate concurrentGate = new TaskerMessagePolicy.LaunchGate(1000L);
        CountDownLatch go = new CountDownLatch(1), done = new CountDownLatch(16);
        AtomicInteger allowed = new AtomicInteger();
        for (int i = 0; i < 16; ++i) {
            Thread worker = new Thread(() -> {
                try { go.await(); if (concurrentGate.tryAcquire(12345)) allowed.incrementAndGet(); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                finally { done.countDown(); }
            });
            worker.start();
        }
        go.countDown(); done.await();
        expect(allowed.get() == 1, "simultaneous broadcasts launched multiple windows");
        System.out.println("PASS: " + checks + " Tasker recipient/text/throttle checks");
    }
}
