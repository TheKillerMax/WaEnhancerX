package com.waenhancer.xposed.features.privacy;

import java.util.Arrays;
import java.util.List;
import java.util.Random;

public final class TestConversationRecipientPolicy {
    private static long checks;
    private static void check(boolean condition, String caseName) {
        checks++;
        if (!condition) throw new AssertionError(caseName);
    }
    public static void main(String[] args) {
        String phone = "14155552671@s.whatsapp.net", other = "14155552672@s.whatsapp.net";
        String lid = "14155552671@lid", group = "14155552671-123456@g.us";
        check(ConversationRecipientPolicy.resolve(null) == null, "null candidates");
        check(ConversationRecipientPolicy.resolve(List.of()) == null, "no candidates");
        check(phone.equals(ConversationRecipientPolicy.resolve(List.of(phone))), "one exact candidate");
        check(phone.equals(ConversationRecipientPolicy.resolve(List.of(phone,phone))), "consistent duplicate");
        check(group.equals(ConversationRecipientPolicy.resolve(List.of(group))), "group recipient");
        check(ConversationRecipientPolicy.resolve(List.of(phone,other)) == null, "two different chats");
        check(ConversationRecipientPolicy.resolve(List.of(phone,lid)) == null, "LID is not phone alias");
        check(ConversationRecipientPolicy.resolve(List.of(phone,group)) == null, "group is not contact");
        check(ConversationRecipientPolicy.resolve(Arrays.asList(phone,null)) == null, "null claimed recipient");
        check(ConversationRecipientPolicy.resolve(List.of(phone,"prefix:"+phone)) == null,
                "embedded identifier must not validate");
        check(ConversationRecipientPolicy.resolve(List.of("prefix:"+phone)) == null,
                "URI or object string not a JID");
        check(ConversationRecipientPolicy.resolve(List.of("status@broadcast")) == null,
                "status identity not supported by manual control");
        Random random = new Random(0xB1E723);
        String[] pool = {phone,other,lid,group};
        for (int n = 0; n < 100_000; n++) {
            String first = pool[random.nextInt(pool.length)];
            String second = pool[random.nextInt(pool.length)];
            boolean expected = first.equals(second);
            String got = ConversationRecipientPolicy.resolve(List.of(first, second));
            check(expected == (got != null), "two-candidate differential at " + n);
            if (expected) check(first.equals(got), "identity changed");
        }
        System.out.println("PASS: " + checks + " manual conversation matching tests");
    }
}
