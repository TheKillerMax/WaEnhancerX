#!/usr/bin/env python3
"""Compile the complete bridge and exact preference receiver callback with JVM substitutes.

Provider transport, Android observer/handler and Binder are controlled boundaries.
Latches establish blocking causality; elapsed time is not an Android performance claim.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('app/src/main/java/com/waenhancer')


def callback(source):
    start = source.index('BroadcastReceiver prefsReceiver =')
    begin = source.index('public void onReceive(', start)
    opening = source.index('{', begin)
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[begin:index + 1]
    raise AssertionError('Unbalanced preference receiver callback')


JAVA = r'''
package test;
import android.content.*;
import android.database.ContentObserver;
import android.net.Uri;
import android.os.Bundle;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class BridgeAsyncChecks {
    static int checks;
    static void check(boolean value, String message) {
        checks++;
        if (!value) throw new AssertionError(message);
    }
    static void await(CountDownLatch latch, String what) throws Exception {
        check(latch.await(3, TimeUnit.SECONDS), "latch timeout: " + what);
    }
    static final class Resolver extends ContentResolver {
        final Map<String, Boolean> values = new ConcurrentHashMap<>();
        final List<Thread> readers = new CopyOnWriteArrayList<>();
        final AtomicInteger reads = new AtomicInteger(), writes = new AtomicInteger();
        volatile CountDownLatch gate, entered;
        Resolver() { values.put("fresh", true); }
        void pause() { entered = new CountDownLatch(1); gate = new CountDownLatch(1); }
        void release() { CountDownLatch current = gate; gate = null; if (current != null) current.countDown(); }
        public void registerContentObserver(Uri uri, boolean descendants, ContentObserver observer) {}
        public Bundle call(Uri uri, String method, String arg, Bundle extras) {
            if ("get_all_preferences".equals(method)) {
                reads.incrementAndGet(); readers.add(Thread.currentThread());
                CountDownLatch current = gate;
                if (current != null) {
                    entered.countDown();
                    try { if (!current.await(5, TimeUnit.SECONDS)) throw new AssertionError("provider held too long"); }
                    catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new AssertionError(error); }
                }
                Bundle snapshot = new Bundle(), result = new Bundle();
                values.forEach(snapshot::putBoolean); result.putBundle("values", snapshot);
                return result;
            }
            if ("apply_preferences".equals(method)) {
                if (extras.getBoolean("clear", false)) values.clear();
                for (Bundle operation : extras.getParcelableArrayList("operations")) {
                    check("boolean".equals(operation.getString("type")), "unexpected write type");
                    values.put(operation.getString("key"), operation.getBoolean("value", false));
                }
                writes.incrementAndGet();
                Bundle result = new Bundle(); result.putBoolean("success", true); return result;
            }
            throw new AssertionError("Unexpected provider method: " + method);
        }
    }
    static final class Ctx extends Context {
        final Resolver resolver = new Resolver();
        public ContentResolver getContentResolver() { return resolver; }
        public String getPackageName() { return "com.whatsapp"; }
    }
    static BroadcastReceiver receiver(final PreferenceBridgeClient bridgeClient) {
        return new BroadcastReceiver() { /* CALLBACK */ };
    }
    static void initial() throws Exception {
        Ctx context = new Ctx(); context.resolver.pause();
        PreferenceBridgeClient bridge = new PreferenceBridgeClient(context, null, true);
        AtomicBoolean completed = new AtomicBoolean();
        Thread waiter = new Thread(() -> { bridge.awaitInitialSync(); completed.set(true); });
        try {
            await(context.resolver.entered, "initial provider read"); waiter.start();
            waiter.join(100);
            check(!completed.get() && waiter.isAlive(), "initial sync returned before the provider finished");
            context.resolver.release(); waiter.join(3000);
            check(completed.get() && !waiter.isAlive(), "initial sync failed to resume");
            check(bridge.getBoolean("fresh", false) && "PROVIDER".equals(bridge.getLastSyncSource()),
                    "authoritative initial snapshot was lost");
            check(context.resolver.reads.get() == 1, "initial read duplicated");
        } finally { context.resolver.release(); waiter.join(3000); }
    }
    static void interrupted() throws Exception {
        Ctx context = new Ctx(); context.resolver.pause();
        PreferenceBridgeClient bridge = new PreferenceBridgeClient(context, null, true);
        AtomicBoolean rejected = new AtomicBoolean(), preserved = new AtomicBoolean();
        CountDownLatch started = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            started.countDown();
            try { bridge.awaitInitialSync(); }
            catch (IllegalStateException expected) { rejected.set(expected.getCause() instanceof InterruptedException); }
            finally { preserved.set(Thread.currentThread().isInterrupted()); }
        });
        try {
            await(context.resolver.entered, "blocked initial read"); waiter.start(); await(started, "waiter start");
            waiter.interrupt(); waiter.join(1000);
            check(!waiter.isAlive(), "interruption left the startup waiter blocked");
            check(rejected.get() && preserved.get(), "interrupted initial wait was swallowed or lost its flag");
            check(!bridge.getBoolean("fresh", false), "blocked read falsely published authoritative data");
            context.resolver.release(); bridge.awaitInitialSync();
            check(bridge.getBoolean("fresh", false) && context.resolver.reads.get() == 1,
                    "interruption cancelled or duplicated the shared initial read");
        } finally { context.resolver.release(); waiter.join(3000); }
    }
    static void refresh() throws Exception {
        Ctx context = new Ctx();
        PreferenceBridgeClient bridge = new PreferenceBridgeClient(context, null);
        BroadcastReceiver receiver = receiver(bridge);
        ExecutorService ui = Executors.newSingleThreadExecutor();
        AtomicReference<Thread> caller = new AtomicReference<>();
        context.resolver.pause();
        try {
            Future<?> first = ui.submit(() -> { caller.set(Thread.currentThread()); receiver.onReceive(context, new Intent()); });
            await(context.resolver.entered, "refresh provider read");
            boolean returned;
            try { first.get(300, TimeUnit.MILLISECONDS); returned = true; }
            catch (TimeoutException blocked) { returned = false; }
            if (!returned) {
                context.resolver.release(); first.get(3, TimeUnit.SECONDS);
                check(false, "preference broadcast blocked its caller on provider I/O");
            }
            Future<?> burst = ui.submit(() -> {
                for (int i = 0; i < 1000; i++) receiver.onReceive(context, new Intent());
                bridge.edit().putBoolean("fresh", false).apply();
            });
            burst.get(1, TimeUnit.SECONDS);
            check(context.resolver.reads.get() == 2, "blocked refresh spawned overlapping provider reads");
            context.resolver.release();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (context.resolver.writes.get() != 1 && System.nanoTime() < deadline) Thread.yield();
            check(context.resolver.writes.get() == 1, "coalesced refresh lost an ordered preference write");
            check(!bridge.getBoolean("fresh", true), "refresh erased accepted optimistic edit");
            check(context.resolver.reads.get() <= 4, "broadcast burst accumulated unbounded refresh tasks");
            check(context.resolver.readers.stream().skip(1).noneMatch(t -> t == caller.get()),
                    "refresh ran on the broadcast caller");
            try { bridge.getAll().clear(); throw new AssertionError("mutable snapshot"); }
            catch (UnsupportedOperationException expected) { check(true, "read-only cache"); }
        } finally { context.resolver.release(); ui.shutdownNow(); }
    }
    public static void main(String[] args) throws Exception {
        switch (args[0]) {
            case "initial": initial(); break;
            case "interrupted": interrupted(); break;
            case "refresh": refresh(); break;
            default: throw new IllegalArgumentException(args[0]);
        }
        System.out.println("PASS " + args[0] + ": " + checks + " bridge/callback checks");
    }
}
'''


def execute(out, main_source, bridge_source):
    main = main_source.read_text(encoding='utf-8')
    extracted = callback(main)
    for marker in ('registerReceiver(prefsReceiver, prefsFilter, RESTART_PERMISSION,',
                   'registerReceiver(prefsReceiver, prefsFilter,\n                                    RESTART_PERMISSION, null)'):
        if marker not in main:
            raise AssertionError('Preference receiver signature permission changed')
    tree = ast.parse((ROOT / 'qa/test_bridge_contract.py').read_text(encoding='utf-8'))
    stubs = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'STUBS' for target in node.targets)))
    stubs.pop('test/BridgeContract.java')
    stubs['android/content/BroadcastReceiver.java'] = 'package android.content; public abstract class BroadcastReceiver {public abstract void onReceive(Context context,Intent intent);}'
    stubs['android/content/Intent.java'] = 'package android.content; public class Intent {}'
    stubs['test/BridgeAsyncChecks.java'] = JAVA.replace('/* CALLBACK */', extracted)
    paths = []
    for name, content in stubs.items():
        path = out / 'generated' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8'); paths.append(path)
    production = [bridge_source, ROOT / BASE / 'config/PreferenceSchema.java',
                  ROOT / BASE / 'xposed/utils/HookErrors.java']
    classes = out / 'classes'; classes.mkdir()
    compiled = subprocess.run(['javac', '--release', '17', '-d', str(classes),
        *map(str, paths + production)], text=True, capture_output=True, timeout=30)
    (out / 'compile.log').write_text(compiled.stdout + compiled.stderr, encoding='utf-8')
    if compiled.returncode:
        raise RuntimeError('Infrastructure failure: compilation; see compile.log')
    results = []
    for case in ('initial', 'interrupted', 'refresh'):
        result = subprocess.run(['java', '-cp', str(classes), 'test.BridgeAsyncChecks', case],
                                text=True, capture_output=True, timeout=15)
        output = result.stdout + result.stderr
        (out / (case + '.log')).write_text(output, encoding='utf-8')
        results.append({'case': case, 'exit': result.returncode, 'output': output})
        print(json.dumps(results[-1]))
    report = {'production_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [main_source, *production]},
              'callback_sha256': hashlib.sha256(extracted.encode()).hexdigest(),
              'fixture_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'results': results, 'scope': 'Complete bridge and extracted actual callback; JVM platform/transport substitutes'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return any(item['exit'] for item in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-source', type=Path, default=ROOT / BASE / 'xposed/MainHook.java')
    parser.add_argument('--bridge-source', type=Path, default=ROOT / BASE / 'xposed/bridge/client/PreferenceBridgeClient.java')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True)
        return execute(args.out, args.main_source, args.bridge_source)
    with tempfile.TemporaryDirectory(prefix='waex-bridge-async-') as directory:
        return execute(Path(directory), args.main_source, args.bridge_source)


if __name__ == '__main__':
    raise SystemExit(main())
