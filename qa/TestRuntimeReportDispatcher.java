package com.waenhancer.xposed.core;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import com.waenhancer.xposed.core.RuntimeReportDispatcher.Kind;

/** Executes the complete production queue; Executor/Binder work is an explicit substitute. */
public final class TestRuntimeReportDispatcher {
    static int checks;
    static void check(boolean value, String message) {
        checks++;
        if (!value) throw new AssertionError(message);
    }
    static final class ManualExecutor implements Executor {
        final Queue<Runnable> tasks = new ArrayDeque<>();
        int submissions;
        boolean reject;
        public void execute(Runnable task) {
            submissions++;
            if (reject) throw new RejectedExecutionException();
            tasks.add(task);
        }
        void run() { tasks.remove().run(); }
    }
    public static void main(String[] args) throws Exception {
        ManualExecutor deferredExecutor = new ManualExecutor();
        List<String> deferred = new ArrayList<>();
        RuntimeReportDispatcher startup = new RuntimeReportDispatcher(deferredExecutor,
                failure -> { throw new AssertionError(failure); }, false);
        startup.submitLatest(Kind.PACKAGE, () -> deferred.add("package"));
        startup.submitLatest(Kind.HEALTH, () -> deferred.add("initializing"));
        startup.submitLatest(Kind.HOOKS, () -> deferred.add("hooks"));
        startup.submitLatest(Kind.HEALTH, () -> deferred.add("ready"));
        check(deferredExecutor.submissions == 0 && deferred.isEmpty(),
                "startup reports ran before lifecycle release");
        startup.release(); startup.release(); startup.release();
        check(deferredExecutor.submissions == 1, "repeated release scheduled duplicate drains");
        deferredExecutor.run();
        check(deferred.equals(List.of("package", "hooks", "ready")),
                "deferred reports lost latest state or inventory order");
        startup.release();
        check(deferredExecutor.submissions == 1, "empty release submitted work");
        startup.submitLatest(Kind.HEALTH, () -> deferred.add("after-release"));
        deferredExecutor.run();
        check(deferred.get(3).equals("after-release"), "post-release report was stranded");

        ManualExecutor catalogueExecutor = new ManualExecutor();
        List<String> catalogueOrder = new ArrayList<>();
        RuntimeReportDispatcher catalogue = new RuntimeReportDispatcher(catalogueExecutor,
                failure -> { throw new AssertionError(failure); }, false);
        catalogue.submitLatest(Kind.HOOKS, () -> catalogueOrder.add("hooks1"));
        catalogue.submitLatest(Kind.HEALTH, () -> catalogueOrder.add("ready"));
        catalogue.submitLatest(Kind.HOOKS, () -> catalogueOrder.add("hooks2"));
        catalogue.release();
        catalogueExecutor.run();
        check(catalogueOrder.equals(List.of("hooks2", "ready")),
                "catalogue replacement moved pending inventory behind READY");

        ManualExecutor raceExecutor = new ManualExecutor();
        List<String> raceDelivered = new ArrayList<>();
        RuntimeReportDispatcher race = new RuntimeReportDispatcher(raceExecutor,
                failure -> { throw new AssertionError(failure); }, false);
        ExecutorService senders = Executors.newFixedThreadPool(4);
        CountDownLatch raceStart = new CountDownLatch(1);
        List<Future<?>> sends = new ArrayList<>();
        try {
            for (int thread = 0; thread < 4; thread++) {
                sends.add(senders.submit(() -> {
                    try { raceStart.await(); } catch (InterruptedException error) { throw new AssertionError(error); }
                    for (int i = 0; i < 1000; i++) {
                        race.submitLatest(Kind.HEALTH, () -> raceDelivered.add("superseded"));
                        race.release();
                    }
                }));
            }
            raceStart.countDown();
            for (Future<?> sender : sends) sender.get(3, TimeUnit.SECONDS);
            race.submitLatest(Kind.HEALTH, () -> raceDelivered.add("terminal"));
            check(raceExecutor.submissions == 1 && raceExecutor.tasks.size() == 1,
                    "release/enqueue race created concurrent or unbounded drains");
            raceExecutor.run();
            check(raceDelivered.equals(List.of("terminal")), "release/enqueue race lost latest report");
        } finally { senders.shutdownNow(); }

        ManualExecutor executor = new ManualExecutor();
        List<String> delivered = new ArrayList<>();
        List<Throwable> errors = new ArrayList<>();
        RuntimeReportDispatcher queue = new RuntimeReportDispatcher(executor, errors::add);
        queue.submitLatest(Kind.PACKAGE, () -> delivered.add("package"));
        queue.submitLatest(Kind.HEALTH, () -> delivered.add("initializing"));
        queue.submitLatest(Kind.HOOKS, () -> delivered.add("hooks"));
        for (int i = 0; i < 100_000; i++) {
            int observation = i;
            queue.submitLatest(Kind.HEALTH, () -> delivered.add("ready:" + observation));
        }
        queue.submitLatest(Kind.UPDATE_CHECK, () -> delivered.add("update"));
        check(delivered.isEmpty(), "submission performed I/O inline");
        check(executor.submissions == 1 && executor.tasks.size() == 1,
                "heartbeats accumulated executor tasks");
        executor.run();
        check(delivered.equals(List.of("package", "hooks", "ready:99999", "update")),
                "latest state must retain causal order after hook inventory: " + delivered);
        check(errors.isEmpty(), "normal delivery emitted a failure");

        queue.submitLatest(Kind.PACKAGE, () -> { throw new IllegalStateException("synthetic"); });
        queue.submitLatest(Kind.HEALTH, () -> delivered.add("recovered"));
        executor.run();
        check(errors.size() == 1 && errors.get(0) instanceof IllegalStateException,
                "delivery failure not isolated");
        check(delivered.get(delivered.size() - 1).equals("recovered"), "failure lost next report");

        executor.reject = true;
        queue.submitLatest(Kind.HEALTH, () -> delivered.add("rejected"));
        check(errors.size() == 2, "rejected worker was not surfaced");
        executor.reject = false;
        queue.submitLatest(Kind.HOOKS, () -> delivered.add("after-reject"));
        executor.run();
        check(!delivered.contains("rejected") && delivered.contains("after-reject"),
                "rejection poisoned future delivery");

        ManualExecutor sinkExecutor = new ManualExecutor();
        RuntimeReportDispatcher badSink = new RuntimeReportDispatcher(sinkExecutor,
                failure -> { throw new IllegalStateException(); });
        badSink.submitLatest(Kind.PACKAGE, () -> { throw new LinkageError(); });
        badSink.submitLatest(Kind.HEALTH, () -> delivered.add("after-sink-failure"));
        sinkExecutor.run();
        check(delivered.contains("after-sink-failure"), "diagnostic sink stopped the queue");

        RuntimeReportDispatcher missingSink = new RuntimeReportDispatcher(sinkExecutor,
                failure -> { throw new NoClassDefFoundError("synthetic logger linkage"); });
        missingSink.submitLatest(Kind.PACKAGE, () -> { throw new IllegalStateException(); });
        missingSink.submitLatest(Kind.HEALTH, () -> delivered.add("after-linkage-sink-failure"));
        sinkExecutor.run();
        check(delivered.contains("after-linkage-sink-failure"),
                "unavailable logger stranded an already pending report");

        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicInteger actualRuns = new AtomicInteger();
        AtomicReference<Thread> worker = new AtomicReference<>();
        AtomicInteger failures = new AtomicInteger();
        RuntimeReportDispatcher blocked = new RuntimeReportDispatcher(f -> failures.incrementAndGet());
        try {
            blocked.submitLatest(Kind.PACKAGE, () -> {
                worker.set(Thread.currentThread()); entered.countDown();
                try { if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("release"); }
                catch (InterruptedException e) { throw new RuntimeException(e); }
            });
            check(entered.await(3, TimeUnit.SECONDS), "worker never reached blocked IPC");
            for (int i = 0; i < 100_000; i++)
                blocked.submitLatest(Kind.HEALTH, actualRuns::incrementAndGet);
            blocked.submitLatest(Kind.HOOKS, finished::countDown);
            check(actualRuns.get() == 0, "blocked Binder spawned replacement workers");
            check(worker.get() != Thread.currentThread() && worker.get().isDaemon(),
                    "optional I/O ran on caller or retained process lifetime");
            check(worker.get().getName().equals("WAEX-Report")
                            && worker.get().getPriority() == Thread.MIN_PRIORITY,
                    "current low-priority reporting worker contract changed");
            release.countDown();
            check(finished.await(3, TimeUnit.SECONDS), "queue failed to resume");
            check(actualRuns.get() == 1 && failures.get() == 0, "blocked backlog was not coalesced");
        } finally { release.countDown(); }
        System.out.println("PASS: " + checks + " runtime queue checks; deferred release, concurrent submission and 200000 replaced observations");
    }
}
