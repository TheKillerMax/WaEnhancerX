package com.waenhancer.xposed.views;

import android.app.Activity;
import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.*;
import android.os.Handler;
import android.view.*;
import android.widget.*;
import com.waenhancer.utils.ContactNameResolver;
import com.waenhancer.xposed.features.customization.IGStatusHook;
import com.whatsapp.jid.UserJid;
import java.lang.ref.WeakReference;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Full production adapter/view, explicit Android/host doubles, real production worker threads. */
public final class TestIGStatusLoading {
    static int checks;
    static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
        checks++;
    }
    static Object field(Object target, String name) throws Exception {
        Field field = target.getClass().getDeclaredField(name); field.setAccessible(true);
        return field.get(target);
    }
    static void setItems(Object... values) {
        synchronized (IGStatusHook.items) {
            IGStatusHook.items.clear(); IGStatusHook.items.addAll(Arrays.asList(values));
        }
    }
    static TextView name(View row) throws Exception { return (TextView) field(row.getTag(), "nameView"); }
    static ImageView photo(View row) throws Exception { return (ImageView) field(row.getTag(), "photoView"); }
    static void expectStart(String jid) throws Exception {
        String started = ContactNameResolver.starts.poll(5, TimeUnit.SECONDS);
        check(jid.equals(started), "load begins for expected row: " + jid + " actual=" + started);
    }
    static void invoke(Object target, String method, Class<?>[] signature, Object... args) throws Exception {
        Method m = target.getClass().getDeclaredMethod(method, signature); m.setAccessible(true); m.invoke(target, args);
    }
    static void waitForWorkToFinish() throws Exception {
        // A barrier job on both workers ensures completed/cancelled earlier work is no longer running.
        Field f = IGStatusAdapter.class.getDeclaredField("ROW_WORK"); f.setAccessible(true);
        StatusRowWorkQueue queue = (StatusRowWorkQueue) f.get(null);
        CountDownLatch loaded = new CountDownLatch(2);
        StatusRowWorkQueue.Target<Object> target = (ticket, value) -> {};
        StatusRowWorkQueue.Dispatcher discard = new StatusRowWorkQueue.Dispatcher() {
            public boolean post(Runnable r) { return false; }
            public void remove(Runnable r) {}
        };
        queue.submit(() -> { loaded.countDown(); if (!loaded.await(5, TimeUnit.SECONDS)) throw new AssertionError("worker barrier"); return null; }, target, discard);
        queue.submit(() -> { loaded.countDown(); if (!loaded.await(5, TimeUnit.SECONDS)) throw new AssertionError("worker barrier"); return null; }, target, discard);
        check(loaded.await(5, TimeUnit.SECONDS), "both workers passed completion barrier");
    }
    public static void main(String[] args) throws Exception {
        ContactNameResolver.ui = Thread.currentThread();
        Context app = new Context(); Activity activity = new Activity(); activity.application = app;
        Files.createDirectories(app.root.toPath().resolve("Avatars"));
        Files.write(app.root.toPath().resolve("Avatars/56912345678@s.whatsapp.net.j"), new byte[]{1});
        Files.write(app.root.toPath().resolve("me.jpg"), new byte[]{1});
        Files.write(app.root.toPath().resolve("status.db"), new byte[]{1});
        setItems(null, new UserJid("56912345678@s.whatsapp.net"));
        IGStatusAdapter adapter = new IGStatusAdapter(activity, Object.class, null);
        ViewGroup parent = new FrameLayout(activity);
        View row = adapter.getView(1, null, parent);
        check(ContactNameResolver.mainIo.get() == 0, "binding performed I/O on the main caller");
        expectStart("56912345678@s.whatsapp.net"); Handler.next();
        check("Name:56912345678@s.whatsapp.net".contentEquals(name(row).text), "resolved contact is delivered");
        check(ContactNameResolver.lastContext == app, "worker receives application context");
        Bitmap avatar = ((BitmapDrawable) photo(row).image).getBitmap();
        check(avatar.getWidth() == 62 && avatar.getHeight() == 62, "final image uses row dimensions");
        check(BitmapFactory.calls.equals(List.of("bounds:file", "sample:file:32")), "file decode reads bounds before sampled pixels");
        View own = adapter.getView(0, null, parent); Handler.next();
        check(ContactNameResolver.mainIo.get() == 0, "own status binding performs database and photo work off caller");

        CountDownLatch releaseA = new CountDownLatch(1);
        ContactNameResolver.barriers.put("11111@s.whatsapp.net", releaseA);
        setItems(null, new UserJid("11111@s.whatsapp.net")); adapter.notifyDataSetChanged();
        row = adapter.getView(1, row, parent); expectStart("11111@s.whatsapp.net");
        Object holder = row.getTag(); Object oldTicket = field(holder, "pending");
        setItems(null, new UserJid("22222@s.whatsapp.net")); adapter.notifyDataSetChanged();
        row = adapter.getView(1, row, parent); expectStart("22222@s.whatsapp.net"); Handler.next();
        check("Name:22222@s.whatsapp.net".contentEquals(name(row).text), "recycled row displays current contact");
        check(((StatusRowWorkQueue.Ticket<?>) oldTicket).isCancelled(), "rebind cancels old generation");
        releaseA.countDown(); waitForWorkToFinish(); Handler.drain();
        check("Name:22222@s.whatsapp.net".contentEquals(name(row).text), "late previous contact cannot replace current row");
        check(field(holder, "pending") == null, "completed row releases its pending ticket");

        CountDownLatch releaseC = new CountDownLatch(1);
        ContactNameResolver.barriers.put("33333@s.whatsapp.net", releaseC);
        setItems(null, new UserJid("33333@s.whatsapp.net")); adapter.notifyDataSetChanged();
        row = adapter.getView(1, row, parent); expectStart("33333@s.whatsapp.net");
        Object cancelled = field(row.getTag(), "pending"); row.detach(); releaseC.countDown();
        waitForWorkToFinish(); Handler.drain();
        check(((StatusRowWorkQueue.Ticket<?>) cancelled).isCancelled(), "detached row cancels active request");
        check("Contact".contentEquals(name(row).text), "detached row receives no late name");
        row.attach(); expectStart("33333@s.whatsapp.net"); Handler.next();
        check("Name:33333@s.whatsapp.net".contentEquals(name(row).text), "reattachment reloads unfinished latest binding");

        Object[] before = IGStatusHook.snapshotItems();
        setItems(null, new UserJid("44444@s.whatsapp.net"), new UserJid("55555@s.whatsapp.net"));
        check(adapter.getCount() == 2, "adapter holds a consistent snapshot before notification");
        adapter.notifyDataSetChanged(); check(adapter.getCount() == 3, "notification acquires latest snapshot");
        check(before.length == 2, "published snapshot stays stable after replacement");
        View invalid = adapter.getView(-1, row, parent);
        check(invalid != row && row.click == null, "invalid position clears recycled click target");

        Field queueField = IGStatusAdapter.class.getDeclaredField("ROW_WORK"); queueField.setAccessible(true);
        StatusRowWorkQueue queue = (StatusRowWorkQueue) queueField.get(null);
        CountDownLatch bothStarted = new CountDownLatch(2), releaseWorkers = new CountDownLatch(1);
        StatusRowWorkQueue.Target<Object> keepTarget = (ticket, result) -> {};
        StatusRowWorkQueue.Dispatcher discard = new StatusRowWorkQueue.Dispatcher() {
            public boolean post(Runnable r) { return false; }
            public void remove(Runnable r) {}
        };
        for (int i = 0; i < 2; i++) queue.submit(() -> {
            bothStarted.countDown();
            if (!releaseWorkers.await(5, TimeUnit.SECONDS)) throw new AssertionError("worker release timed out");
            return null;
        }, keepTarget, discard);
        check(bothStarted.await(5, TimeUnit.SECONDS), "both production workers held before queued bind");
        View queuedRow = adapter.getView(1, null, parent);
        Object queuedTicket = field(queuedRow.getTag(), "pending");
        Object work = field(queuedTicket, "work");
        check(work != null, "row is queued while workers are occupied");
        for (Field capture : work.getClass().getDeclaredFields()) {
            capture.setAccessible(true); Object captured = capture.get(work);
            check(!(captured instanceof Activity) && !(captured instanceof View) && captured != adapter,
                    "compiled work closure has no Activity, view or adapter capture");
        }
        queuedRow.detach(); releaseWorkers.countDown(); waitForWorkToFinish(); Handler.drain();
        check(ContactNameResolver.starts.isEmpty(), "detaching queued row removes its I/O before execution");
        java.lang.ref.Reference.reachabilityFence(keepTarget);

        Method placeholder = IGStatusAdapter.class.getDeclaredMethod("createDefaultAvatarDrawable");
        placeholder.setAccessible(true);
        Bitmap firstPlaceholder = ((BitmapDrawable) placeholder.invoke(adapter)).getBitmap();
        check(((BitmapDrawable) placeholder.invoke(adapter)).getBitmap() == firstPlaceholder, "same row dimensions/theme share placeholder pixels");
        activity.resources.config.uiMode = 32;
        Bitmap darkPlaceholder = ((BitmapDrawable) placeholder.invoke(adapter)).getBitmap();
        check(darkPlaceholder != firstPlaceholder, "theme change rebuilds placeholder");
        activity.resources.metrics.density = 2;
        Bitmap densePlaceholder = ((BitmapDrawable) placeholder.invoke(adapter)).getBitmap();
        check(densePlaceholder != darkPlaceholder && densePlaceholder.getWidth() == 124, "density change rebuilds correctly sized placeholder");

        Method contactPhoto = IGStatusAdapter.class.getDeclaredMethod("loadContactPhoto", Context.class, String.class, int.class);
        contactPhoto.setAccessible(true);
        Path pnAvatar = app.root.toPath().resolve("Avatars/123456@s.whatsapp.net.j");
        Files.write(pnAvatar, new byte[]{1});
        check(contactPhoto.invoke(null, app, "123456@lid", 62) == null,
                "LID must not borrow same-number PN avatar without a verified alias");
        Files.write(app.root.toPath().resolve("Avatars/123456@lid.j"), new byte[]{1});
        check(contactPhoto.invoke(null, app, "123456@lid", 62) != null, "exact LID avatar remains available");
        Files.delete(app.root.toPath().resolve("Avatars/123456@lid.j")); Files.delete(pnAvatar);
        Files.createDirectories(app.root.toPath().resolve("Profile Pictures"));
        Files.write(app.root.toPath().resolve("Profile Pictures/123456.jpg"), new byte[]{1});
        check(contactPhoto.invoke(null, app, "123456@lid", 62) == null, "LID must not borrow same-number phone cache");
        check(contactPhoto.invoke(null, app, "123456@g.us", 62) == null, "group must not borrow same-number phone cache");
        check(contactPhoto.invoke(null, app, "123456@s.whatsapp.net", 62) != null, "verified phone namespace retains phone cache fallback");
        Files.write(app.root.toPath().resolve("Avatars/123456@lid.evil.j"), new byte[]{1});
        check(contactPhoto.invoke(null, app, "123456@lid.evil", 62) == null, "unsupported identity cannot select an avatar path");

        // Decode overloads and final crop are the complete production methods, invoked directly.
        Method decode = IGStatusAdapter.class.getDeclaredMethod("decodeThumbnail", byte[].class, int.class);
        decode.setAccessible(true); BitmapFactory.calls.clear();
        Bitmap decoded = (Bitmap) decode.invoke(null, new byte[]{1, 2}, 62);
        check(decoded.getWidth() == 125 && decoded.getHeight() == 94, "blob decode obeys longest-edge allocation bound");
        check(BitmapFactory.calls.equals(List.of("bounds:blob", "sample:blob:32")), "blob decode uses bounds and sample");
        BitmapFactory.width = -1; BitmapFactory.calls.clear();
        check(decode.invoke(null, new byte[]{1}, 62) == null && BitmapFactory.calls.equals(List.of("bounds:blob")), "invalid headers stop before pixel allocation");
        BitmapFactory.width = 4000;
        Method circle = IGStatusAdapter.class.getDeclaredMethod("toCircleDrawable", Context.class, Drawable.class, int.class);
        circle.setAccessible(true);
        BitmapDrawable cropped = (BitmapDrawable) circle.invoke(null, app, new BitmapDrawable(app.resources, new Bitmap(400, 200)), 62);
        BitmapShader shader = (BitmapShader) Canvas.lastCirclePaint.shader;
        check(cropped.getBitmap().getWidth() == 62 && cropped.getBitmap().getHeight() == 62, "crop allocates final row-sized square");
        check(Math.abs(shader.matrix.sx - .31f) < .0001f && Math.abs(shader.matrix.tx + 31f) < .0001f && shader.matrix.ty == 0, "wide image is scaled and center cropped");
        Drawable vector = new Drawable(); circle.invoke(null, app, vector, 9999);
        check(vector.width == 512 && vector.height == 512, "non-bitmap intrinsic dimensions cannot drive large allocation");

        Handler.drain();
        IGStatusView view = new IGStatusView(activity); BaseAdapter counted = new BaseAdapter(); view.setAdapter(counted);
        for (int i = 0; i < 100; i++) view.updateList();
        check(Handler.queue.size() == 1, "burst schedules one refresh"); Handler.next();
        check(counted.notifications == 1, "burst notifies once");
        counted.onNotify = () -> { counted.onNotify = null; view.updateList(); };
        view.updateList(); Handler.next();
        check(Handler.queue.size() == 1, "update during notification schedules the latest pass"); Handler.next();
        check(counted.notifications == 3, "coalescing does not lose reentrant refresh");
        view.updateList(); view.detach();
        check(Handler.queue.isEmpty(), "detach removes queued refresh");
        view.updateList(); check(Handler.queue.isEmpty(), "detached container does not accumulate work");
        view.attach(); Handler.next(); check(counted.notifications == 4, "attach refreshes newest data once");
        Handler.accept = false; view.updateList(); Handler.accept = true; view.updateList();
        Handler.next(); check(counted.notifications == 5, "failed post permits a later refresh");

        IGStatusHook.register(7, view);
        IGStatusView replacement = new IGStatusView(activity); IGStatusHook.register(7, replacement);
        Field containers = IGStatusHook.class.getDeclaredField("statusContainers"); containers.setAccessible(true);
        List<?> registry = (List<?>) containers.get(null);
        check(registry.size() == 1 && ((WeakReference<?>) registry.get(0)).get() == replacement, "registry replaces duplicate fragment with a weak entry");
        ((WeakReference<?>) registry.get(0)).clear();
        Method update = IGStatusHook.class.getDeclaredMethod("updateAllContainers"); update.setAccessible(true); update.invoke(null);
        check(registry.isEmpty(), "notification safely prunes collected containers");
        System.out.println("PASS: " + checks + " real adapter/view binding, sampling, cancellation and lifecycle checks (Android API doubles)");
    }
}
