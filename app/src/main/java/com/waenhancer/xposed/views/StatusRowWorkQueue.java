package com.waenhancer.xposed.views;

import java.lang.ref.WeakReference;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded off-thread row work; queued work and UI deliveries can be cancelled. */
final class StatusRowWorkQueue implements AutoCloseable {
    interface Work<T> { T load() throws Exception; }
    interface Target<T> { void onLoaded(Ticket<T> ticket, T result); }
    interface Dispatcher {
        boolean post(Runnable delivery);
        void remove(Runnable delivery);
    }

    private final ThreadPoolExecutor workers;

    StatusRowWorkQueue(int threads, int capacity) {
        AtomicInteger names = new AtomicInteger();
        workers = new ThreadPoolExecutor(threads, threads, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(capacity), work -> {
                    Thread thread = new Thread(work, "WAEX-Status-" + names.incrementAndGet());
                    thread.setDaemon(true);
                    return thread;
                }, new ThreadPoolExecutor.AbortPolicy());
        workers.allowCoreThreadTimeOut(true);
    }

    <T> Ticket<T> submit(Work<T> work, Target<T> target, Dispatcher dispatcher) {
        Ticket<T> ticket = new Ticket<>(workers, work, target, dispatcher);
        try {
            workers.execute(ticket);
        } catch (RejectedExecutionException rejected) {
            // A busy loader leaves the placeholder; it must never run I/O on the UI caller.
            ticket.cancel();
        }
        return ticket;
    }

    @Override public void close() {
        for (Runnable work : workers.shutdownNow()) {
            if (work instanceof Ticket<?>) ((Ticket<?>) work).cancel();
        }
    }

    static final class Ticket<T> implements Runnable {
        private final ThreadPoolExecutor workers;
        private final WeakReference<Target<T>> target;
        private final Dispatcher dispatcher;
        private Work<T> work;
        private boolean cancelled;
        private Runnable delivery;
        private T result;

        Ticket(ThreadPoolExecutor workers, Work<T> work, Target<T> target, Dispatcher dispatcher) {
            this.workers = workers;
            this.work = work;
            this.target = new WeakReference<>(target);
            this.dispatcher = dispatcher;
        }

        synchronized boolean isCancelled() { return cancelled; }

        void cancel() {
            synchronized (this) {
                cancelled = true;
                work = null;
                result = null;
                target.clear();
                if (delivery != null) dispatcher.remove(delivery);
                delivery = null;
            }
            workers.remove(this);
        }

        @Override public void run() {
            Work<T> selected;
            synchronized (this) {
                if (cancelled || target.get() == null) { work = null; return; }
                selected = work;
                work = null;
            }
            T loaded = null;
            try {
                if (selected != null) loaded = selected.load();
            } catch (Exception | LinkageError ignored) {
                // An unavailable row keeps its placeholder. Do not log contact/path payloads.
            }
            synchronized (this) {
                if (cancelled || target.get() == null) return;
                result = loaded;
                delivery = this::deliver;
                if (!dispatcher.post(delivery)) {
                    result = null;
                    delivery = null;
                    target.clear();
                }
            }
        }

        private void deliver() {
            Target<T> current;
            T loaded;
            synchronized (this) {
                if (cancelled) return;
                current = target.get();
                loaded = result;
                result = null;
                delivery = null;
                target.clear();
            }
            if (current != null) current.onLoaded(this, loaded);
        }
    }
}
