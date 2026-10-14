package com.waenhancer.xposed.features.privacy;

import java.util.Random;

public final class TestExplicitReadReceiptPolicy {
    private static int checks;
    private static void require(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        RecipientReceiptAllowance grants = new RecipientReceiptAllowance(120_000L, 64);
        String target = "14155552671@s.whatsapp.net";
        String other = "14155552672@s.whatsapp.net";
        grants.allow(target, "M", 100L);
        String[] forbidden = { null, "", "delivery", "delivered", "inactive", "receipt",
            "readstatus", "played", "server", "retry", "READ", "read ", "read\n" };
        for (String type : forbidden) {
            require(!ExplicitReadReceiptPolicy.maySend(type,target,"M",false,grants,100L),
                    "non-read receipt permitted: " + type);
        }
        require(ExplicitReadReceiptPolicy.maySend("read",target,"M",false,grants,100L),
                "explicit read stanza must be allowed");
        require(!ExplicitReadReceiptPolicy.maySend("read",target,"M",true,grants,100L),
                "delivery hiding / Ghost Mode must take priority");
        require(!ExplicitReadReceiptPolicy.maySend("read",other,"M",false,grants,100L),
                "recipient must match");
        require(!ExplicitReadReceiptPolicy.maySend("read",target,"N",false,grants,100L),
                "message ID must match");
        require(!ExplicitReadReceiptPolicy.maySend("read",target,null,false,grants,100L),
                "unknown ID denied");
        require(!ExplicitReadReceiptPolicy.maySend("read",target,"M",false,null,100L),
                "missing grants denied");
        require(!ExplicitReadReceiptPolicy.maySend("read",target,"M",false,grants,120_101L),
                "expired ID denied");
        grants.allow(target,"R",1000L);
        Random random = new Random(0x44BEEFL);
        for (int i=0;i<100000;i++) {
            int kind = random.nextInt(10);
            boolean hideDelivery = random.nextBoolean();
            String type = kind == 0 ? "read" : forbidden[kind];
            boolean expected = kind == 0 && !hideDelivery;
            require(ExplicitReadReceiptPolicy.maySend(type,target,"R",hideDelivery,grants,1000L)==expected,
                    "read exception was granted beyond its narrow scope at iteration "+i);
        }
        System.out.println("PASS: " + checks + " exact-read and delivery/Ghost Mode isolation assertions");
    }
}
