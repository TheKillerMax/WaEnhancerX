package com.waenhancer.xposed.features.privacy;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class TestBoundedReceiptAllowance {
    private static int checks;
    private static void check(boolean condition,String message){checks++;if(!condition)throw new AssertionError(message);}
    public static void main(String[] args) throws Exception {
        BoundedReceiptAllowance allowed=new BoundedReceiptAllowance(120000L,3);
        check(!allowed.isAllowed("msgA",0),"unknown ID denied");
        allowed.allow("msgA",100);
        check(allowed.isAllowed("msgA",100),"immediate allowance");
        check(allowed.isAllowed("msgA",120100),"boundary inclusive");
        check(!allowed.isAllowed("msgA",120101),"allowance expired");
        check(allowed.countForTests()==0,"expiration purges stale ID");
        check(!allowed.isAllowed("msgB",100),"different ID denied");
        allowed.allow(null,1);allowed.allow("",1);allowed.allow("bad",-1);
        check(allowed.countForTests()==0,"invalid entries rejected");
        allowed.allow("old",1);allowed.allow("fresh",10000000);
        check(allowed.countForTests()==2,"old ID still bounded until next insertion");
        allowed.allow("future",10000000);allowed.allow("next",10000000);
        check(allowed.countForTests()<=3,"capacity bounded");
        check(!allowed.isAllowed("old",10000000),"expired old key removed");
        check(allowed.isAllowed("future",10000000),"fresh ID kept");
        allowed.allow("tick",10000000);
        check(!allowed.isAllowed("tick",9999999),"monotonic rollback denied");
        check(!allowed.isAllowed("tick",10000000),"rollback purges allowance");
        boolean failed=false;
        try {new BoundedReceiptAllowance(0,1);}catch(IllegalArgumentException e){failed=true;}
        check(failed,"zero TTL denied");
        failed=false;
        try {new BoundedReceiptAllowance(1,0);}catch(IllegalArgumentException e){failed=true;}
        check(failed,"zero max denied");
        BoundedReceiptAllowance shared=new BoundedReceiptAllowance(10000,100);
        CountDownLatch finish=new CountDownLatch(6);AtomicInteger faults=new AtomicInteger();
        for(int i=0;i<6;i++){
          final int id=i;
          new Thread(()->{
            try{for(int j=0;j<5000;j++) {String k="w"+id+"-"+j;
                shared.allow(k,1000+j);
                // A concurrent eviction is legitimate; the check exercises the lock.
                shared.isAllowed(k,1000+j);
            }}catch(Throwable e){faults.incrementAndGet();}finally{finish.countDown();}
          }).start();
        }
        finish.await();
        // Concurrent eviction may remove a key between allow/isAllowed; the
        // global size/exception-safety invariant still holds.
        check(faults.get()==0,"concurrent grants and reads have no exceptions");
        check(shared.countForTests()<=100,"30,000 concurrent grants bounded");
        System.out.println("PASS: "+checks+" allowance/TTL checks and 30,000 concurrent writes");
    }
}
