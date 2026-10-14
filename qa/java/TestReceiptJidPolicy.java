package com.waenhancer.xposed.features.privacy;

import java.util.Random;

/** Standalone JDK check of strict receiver matching; no WhatsApp APK required. */
public final class TestReceiptJidPolicy {
    private static int assertions;

    private static void expect(boolean result, String description) {
        assertions++;
        if (!result) throw new AssertionError(description);
    }

    public static void main(String[] args) {
        String[] allowed = {
                "14155552671@s.whatsapp.net", "1234567890-1630000000@g.us",
                "12345678901234567890@lid", "1234567890@broadcast",
                "7@s.whatsapp.net", "123456789@g.us", "0@lid"
        };
        for (String jid : allowed) {
            expect(jid.equals(ReceiptJidPolicy.canonical(jid)), "legitimate exact recipient rejected");
        }

        String[] rejected = {
                null, "", " ", " 14155552671@s.whatsapp.net", "14155552671@s.whatsapp.net ",
                "evil:14155552671@s.whatsapp.net", "jid=14155552671@s.whatsapp.net",
                "jid(14155552671@s.whatsapp.net)", "14155552671@s.whatsapp.net.evil",
                "14155552671@s.whatsapp.net/path", "14155552671@s.whatsapp.net?device=3",
                "14155552671@s.whatsapp.net#note", "14155552671:4@s.whatsapp.net",
                "14155552671@s.whatsapp.net,12345@lid", "123@g.us;other@lid",
                "123-@g.us", "-123@g.us", "123--456@g.us",
                "status@broadcast", "14155552671@c.us", "14155552671@whatsapp.net",
                "14155552671@LID", "١٤١٥٥٥٥٢٦٧١@s.whatsapp.net",
                "14\n155552671@s.whatsapp.net", "14\u000055552671@s.whatsapp.net",
                "a@lid", "a234@g.us", "123@lid.evil"
        };
        for (String value : rejected) {
            expect(ReceiptJidPolicy.canonical(value) == null,
                    "malformed or embedded JID accepted: " + value);
        }

        // A phone JID must not resolve to an LID or a group sharing the same prefix.
        expect(!ReceiptJidPolicy.canonical(allowed[0]).equals(allowed[2]), "namespace collapse");
        Random random = new Random(0x51A7BEEFL);
        String target = "14155552671@s.whatsapp.net";
        String[] prefix = {"x", " ", "a.", "http://", "id=", "(", "\n", "---"};
        String[] suffix = {".evil", "!", " ", "/path", "?x=y", ")", "\n", ";"};
        for (int i = 0; i < 80_000; i++) {
            String s = (random.nextBoolean() ? prefix[random.nextInt(prefix.length)] : "")
                    + target
                    + (random.nextBoolean() ? suffix[random.nextInt(suffix.length)] : "");
            expect((ReceiptJidPolicy.canonical(s) != null) == target.equals(s),
                    "substring routing accepted at case " + i);
        }
        expect(ReceiptJidPolicy.canonical("1".repeat(125) + "@lid") == null,
                "oversized JID accepted");
        System.out.println("PASS: " + assertions + " exact JID and negative-case checks");
    }
}
