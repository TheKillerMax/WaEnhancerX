package com.waenhancer.xposed.features.media;

import X.Chat;
import X.Data;
import X.Key;
import X.Media;
import X.Message;
import android.content.Context;
import android.content.SharedPreferences;
import android.view.Menu;
import android.view.MenuInflater;
import android.view.MenuItem;
import androidx.fragment.app.Fragment;
import androidx.viewpager.widget.ViewPager;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.whatsapp.infra.core.jid.Jid;
import com.whatsapp.mediaview.MediaViewFragment;
import com.whatsapp.mediaview.menu.MediaViewMenu;
import com.whatsapp.mediaview.ui.MediaViewBaseFragment;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.result.MethodData;
import org.luckypray.dexkit.result.UsingFieldData;

import java.io.File;
import java.io.IOException;
import java.lang.ref.WeakReference;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Behavioral fixture. Class names and members intentionally differ from the host obfuscation. */
public final class ViewOnceDownloadTest {
    static int checks;
    static final int ID = 0x7EAD0003;
    static final ClassLoader LOADER = ViewOnceDownloadTest.class.getClassLoader();
    static final Context APP = new Context();
    static final class Prefs implements SharedPreferences {
        volatile boolean enabled = true;
        volatile boolean fail;
        public boolean getBoolean(String key, boolean fallback) {
            if (fail) throw new ClassCastException("fixture preference");
            return key.equals("downloadviewonce") ? enabled : fallback;
        }
    }
    static final class Item implements MenuItem {
        final int id;
        OnMenuItemClickListener listener;
        Item(int id) { this.id = id; }
        public void setShowAsAction(int value) { }
        public MenuItem setIcon(android.graphics.drawable.Drawable value) { return this; }
        public MenuItem setOnMenuItemClickListener(OnMenuItemClickListener value) { listener = value; return this; }
        boolean click() { return listener.onMenuItemClick(this); }
    }
    static final class MenuDouble implements Menu {
        final Map<Integer, Item> items = new HashMap<>();
        public MenuItem findItem(int id) { return items.get(id); }
        public MenuItem add(int group, int id, int order, CharSequence title) {
            if (items.containsKey(id)) throw new AssertionError("Duplicate menu ID");
            Item item = new Item(id); items.put(id, item); return item;
        }
        public void removeItem(int id) { items.remove(id); }
        Item item() { return items.get(ID); }
    }
    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        checks++;
    }
    static Method method(Class<?> owner, String name, Class<?>... arguments) throws Exception {
        return owner.getDeclaredMethod(name, arguments);
    }
    static Field field(Class<?> owner, String name) throws Exception { return owner.getDeclaredField(name); }
    static MethodData data(DexKitBridge bridge, Method method) {
        return bridge.entries.computeIfAbsent(method, MethodData::new);
    }
    static void calls(DexKitBridge bridge, Method method, Method... called) {
        MethodData row = data(bridge, method);
        for (Method next : called) row.calls.add(data(bridge, next));
    }
    static void reads(DexKitBridge bridge, Method method, Field... fields) {
        for (Field field : fields) data(bridge, method).fields.add(new UsingFieldData(field));
    }
    static Method create, prepare, selected, clicked, selectEvent;
    static DexKitBridge metadata() throws Exception {
        DexKitBridge bridge = new DexKitBridge();
        create = method(MediaViewFragment.class, "create", MenuInflater.class, Menu.class);
        prepare = method(MediaViewFragment.class, "prepare", Menu.class);
        selected = method(MediaViewFragment.class, "selected", MediaViewFragment.class, int.class);
        clicked = method(MediaViewMenu.class, "clickHost", MenuItem.class, Fragment.class, Media.class, int.class);
        selectEvent = method(MediaViewFragment.class, "onOptionsItemSelected", MenuItem.class);
        calls(bridge, selectEvent, selected, clicked);
        calls(bridge, create, method(MediaViewMenu.class, "createHost", Context.class, Menu.class,
                Fragment.class, Chat.class, Message.class, int.class, boolean.class));
        calls(bridge, prepare, selected, method(ViewPager.class, "getCurrentItem"));
        calls(bridge, method(MediaViewFragment.class, "unrelatedPrepare", Menu.class));
        Method canonical = method(Data.class, "canonicalFile");
        calls(bridge, clicked, canonical, canonical); // Repeated bytecode edges are not ambiguity.
        MethodData constructor = new MethodData(null); constructor.callable = false;
        data(bridge, clicked).calls.add(constructor);
        MethodData optionalService = new MethodData(method(String.class,"length"));
        optionalService.ownerOverride="missing.OptionalEditorService";
        optionalService.unavailable=true;
        data(bridge, clicked).calls.add(optionalService);
        data(bridge, selectEvent).calls.add(optionalService);
        reads(bridge, prepare, field(MediaViewBaseFragment.class, "page"));
        reads(bridge, clicked, field(Media.class, "data"), field(Message.class, "key"), field(Key.class, "chat"));
        bridge.fallback = create;
        return bridge;
    }
    static ViewOnceMediaResolver.Contract contract(DexKitBridge bridge) throws Exception {
        return ViewOnceMediaResolver.discover(bridge, LOADER);
    }
    static File file(String name) throws IOException {
        File result = Files.createTempFile("view-once-" + name, ".jpg").toFile();
        Files.write(result.toPath(), new byte[]{(byte)255,(byte)216,(byte)255,42});
        result.deleteOnExit(); return result;
    }
    static Media media(File path, String jid, String id, boolean own) {
        return new Media(new Key(new Chat(jid), id, own), new Data(path == null ? null : path.getPath()));
    }
    static MediaViewFragment viewer(Media... values) {
        MediaViewFragment viewer = new MediaViewFragment(); viewer.messages = values; return viewer;
    }
    static void invokeMenu(Method method, Object viewer, MenuDouble menu, Throwable failure) throws Throwable {
        XC_MethodHook callback = XposedBridge.hooks.get(method);
        check("Expected actual menu method was hooked: " + method.getName(), callback != null);
        XC_MethodHook.MethodHookParam parameters = new XC_MethodHook.MethodHookParam();
        parameters.thisObject = viewer;
        parameters.args = method.equals(create) ? new Object[]{new MenuInflater(), menu} : new Object[]{menu};
        parameters.failure = failure;
        Object[] savedArguments = parameters.args.clone();
        callback.runAfter(parameters);
        check("Host exception unchanged", parameters.failure == failure);
        check("Host argument array unchanged", java.util.Arrays.equals(parameters.args, savedArguments));
    }
    @SuppressWarnings("unchecked") static AtomicReference<Object> active() throws Exception {
        Field field = field(DownloadViewOnceHook.class, "EXPORTING"); field.setAccessible(true);
        return (AtomicReference<Object>) field.get(null);
    }
    static ThreadPoolExecutor worker() throws Exception {
        Class<?> type = Class.forName(DownloadViewOnceHook.class.getName() + "$ExportWorker");
        Field field = field(type, "INSTANCE"); field.setAccessible(true); return (ThreadPoolExecutor) field.get(null);
    }
    static void idle() throws Exception {
        long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (active().get() != null && System.nanoTime() < end) Thread.sleep(1);
        check("Export reservation released", active().get() == null);
    }
    static void invalid(String label, java.util.function.Consumer<DexKitBridge> change) throws Exception {
        DexKitBridge bridge = metadata(); change.accept(bridge);
        boolean rejected = false;
        try { contract(bridge); } catch (IllegalArgumentException expected) { rejected = true; }
        check("Reject " + label, rejected);
    }
    static void resolverChecks() throws Exception {
        ViewOnceMediaResolver.Contract contract = contract(metadata());
        check("Correct menu creation order", contract.createMenu.equals(create));
        check("Correct preparation instead of arbitrary Menu overload", contract.prepareMenu.equals(prepare));
        File first = file("first"), second = file("second"), misleading = file("thumbnail");
        Media a = media(first, "123@s.whatsapp.net", "same", false);
        Media b = media(second, "123@lid", "same", true);
        b.unrelated = misleading; b.data.thumbnail = misleading;
        MediaViewFragment viewer = viewer(a, b);
        viewer.page.index = 1;
        check("Current page instead of initial message", second.equals(contract.fileAtCurrentPage(viewer)));
        check("Canonical lazy getter executed", b.data.calls == 1);
        check("Zero initial getter calls", viewer.initialCalls == 0);
        check("Unrelated and thumbnail Files ignored", !misleading.equals(contract.fileAtCurrentPage(viewer)));
        viewer.page.index = 0;
        check("Navigate back to first message", first.equals(contract.fileAtCurrentPage(viewer)));
        viewer.page.index = -1; check("Negative page", contract.fileAtCurrentPage(viewer) == null);
        viewer.page.index = 9; check("Out of range page", contract.fileAtCurrentPage(viewer) == null);
        check("Foreign receiver", contract.fileAtCurrentPage(new Object()) == null);
        check("Null receiver", contract.fileAtCurrentPage(null) == null);
        viewer.page = null; check("Detached pager", contract.fileAtCurrentPage(viewer) == null);
        for (Media missing : new Media[]{null, new Media(null, new Data(first.getPath())),
                new Media(new Key(null,"key",false),new Data(first.getPath())),
                media(first,"123@lid","",false),media(first,"","id",false),
                media(null,"123@lid","id",false)}) {
            check("Unavailable or unidentified media", contract.fileAtCurrentPage(viewer(missing)) == null);
        }
        Media missingData = media(first,"123@lid","id",false); missingData.data = null;
        check("Missing data", contract.fileAtCurrentPage(viewer(missingData)) == null);
        for (String changed : new String[]{"id","jid","own","data","page","pager","message-null"}) {
            Media original = media(first,"123@lid","id",false);
            MediaViewFragment changing = viewer(original, media(second,"other@lid","other",false));
            original.data.during = () -> {
                Media replacement = media(first,
                        changed.equals("jid") ? "123@s.whatsapp.net" : "123@lid",
                        changed.equals("id") ? "other" : "id", changed.equals("own"));
                if (!changed.equals("data")) replacement.data = original.data;
                switch (changed) {
                    case "page": changing.page.index = 1; break;
                    case "pager": changing.page = new X.Page(); break;
                    case "message-null": changing.messages[0] = null; break;
                    default: changing.messages[0] = replacement;
                }
            };
            check("Reject selection change during canonical getter: " + changed,
                    contract.fileAtCurrentPage(changing) == null);
        }
        Media fails = media(first,"123@lid","key",false);
        fails.data.during = () -> { throw new IllegalStateException("private media path"); };
        boolean threw = false;
        try { contract.fileAtCurrentPage(viewer(fails)); }
        catch (java.lang.reflect.InvocationTargetException expected) { threw = true; }
        check("Host getter exception stays failure", threw);
        fails.data.during = null; fails.data.fatal = new OutOfMemoryError("fixture fatal");
        threw = false;
        try { contract.fileAtCurrentPage(viewer(fails)); } catch (OutOfMemoryError expected) { threw = true; }
        check("Fatal reflected error not hidden", threw);

        invalid("missing current selector edge", d -> d.entries.get(selectEvent).calls.removeIf(x -> selected.equals(x.method)));
        invalid("ambiguous current selectors", d -> {
            try { calls(d, selectEvent, method(MediaViewFragment.class,"decoy",MediaViewFragment.class,int.class)); }
            catch (Exception e) { throw new AssertionError(e); }
        });
        invalid("missing preparation edge", d -> d.entries.get(prepare).calls.clear());
        invalid("ambiguous preparation callbacks", d -> {
            try { calls(d, method(MediaViewFragment.class,"unrelatedPrepare",Menu.class),
                    selected,method(ViewPager.class,"getCurrentItem")); }
            catch (Exception e) { throw new AssertionError(e); }
        });
        invalid("missing pager field", d -> d.entries.get(prepare).fields.clear());
        invalid("ambiguous pager fields", d -> {
            try { reads(d,prepare,field(MediaViewBaseFragment.class,"decoyPage")); }
            catch (Exception e) { throw new AssertionError(e); }
        });
        invalid("pager only written, not read", d -> d.entries.get(prepare).fields.get(0).type=org.luckypray.dexkit.result.FieldUsingType.Write);
        invalid("file accessor missing", d -> d.entries.get(clicked).calls.clear());
        invalid("file accessor ambiguous", d -> {
            try { calls(d,clicked,method(Data.class,"wrongFile")); } catch (Exception e) { throw new AssertionError(e); }
        });
        invalid("data member missing", d -> d.entries.get(clicked).fields.removeIf(x -> x.field.field.getName().equals("data")));
        invalid("data members ambiguous", d -> {
            try { reads(d,clicked,field(Media.class,"decoyData")); } catch (Exception e) { throw new AssertionError(e); }
        });
        invalid("primary key edge missing", d -> d.entries.get(clicked).fields.removeIf(x -> x.field.field.getName().equals("key")));
        invalid("menu initializer edge missing", d -> d.entries.get(create).calls.clear());
    }
    static void installationChecks() throws Throwable {
        DexSearchEngine.bridge = metadata();
        DownloadViewOnceHook hook = new DownloadViewOnceHook(APP, LOADER, new Prefs());
        for (int failing : new int[]{1,2}) {
            XposedBridge.hooks.clear(); XposedBridge.installs=0; XposedBridge.unhooks=0;
            XposedBridge.failAt=failing; hook.hook();
            check("Failed menu registration leaves no partial callback " + failing, XposedBridge.hooks.isEmpty());
            check("Rollback uses only the returned handle " + failing, XposedBridge.unhooks==failing-1);
        }
        XposedBridge.hooks.clear(); XposedBridge.installs=0; XposedBridge.unhooks=0;
        XposedBridge.failAt=2; XposedBridge.fatal=new OutOfMemoryError("/private/fixture-secret-install");
        boolean propagated=false;
        try { hook.hook(); } catch (OutOfMemoryError failure) { propagated=failure==XposedBridge.fatal; }
        finally { XposedBridge.fatal=null; XposedBridge.failAt=0; }
        check("Fatal installation failure propagates after rollback",propagated&&XposedBridge.hooks.isEmpty()&&XposedBridge.unhooks==1);
        hook.hook();
        check("Clean retry installs the complete menu pair",XposedBridge.hooks.size()==2);
        XposedBridge.hooks.clear();
    }
    static void hookChecks() throws Throwable {
        DexSearchEngine.bridge = metadata();
        Prefs prefs = new Prefs();
        DownloadViewOnceHook hook = new DownloadViewOnceHook(APP, LOADER, prefs);
        XposedBridge.hooks.clear(); hook.hook();
        check("Only verified photo/video create and prepare hooks", XposedBridge.hooks.size() == 2);
        File first = file("first"), second = file("second");
        Media a = media(first,"one@lid","a",false), b = media(second,"two@lid","b",true);
        MediaViewFragment viewer = viewer(a,b);
        MenuDouble menu = new MenuDouble(); menu.add(0,19,0,"Host action");
        com.waenhancer.xposed.features.homescreen.MenuIconLoader.missing = true;
        invokeMenu(create,viewer,menu,null);
        check("Download action added", menu.item() != null);
        check("Missing icon retains functional text action", menu.item().listener != null);
        com.waenhancer.xposed.features.homescreen.MenuIconLoader.missing = false;
        for (int i=0;i<100;i++) invokeMenu(prepare,viewer,menu,null);
        check("No duplicate action", menu.items.size() == 2);
        check("No selected-message lookup in menu preparation", viewer.selectedCalls == 0);
        check("No File getter in menu preparation", a.data.calls == 0 && b.data.calls == 0);
        viewer.page.index = 1;
        check("Explicit click consumed",menu.item().click()); idle();
        check("After navigation exports current file", GalleryMediaExporter.exported.equals(List.of(second)));
        check("Copy dispatched off click caller", "WAEX-view-once-export".equals(GalleryMediaExporter.thread));

        Item old = menu.item(); prefs.enabled = false;
        invokeMenu(prepare,viewer,menu,null);
        check("Disabled option removes only module item", menu.item()==null && menu.items.containsKey(19));
        old.click(); check("Removed listener rechecks option", GalleryMediaExporter.exported.size()==1);
        prefs.enabled = true; invokeMenu(prepare,viewer,menu,null);
        invokeMenu(prepare,viewer,menu,new IllegalStateException("host error"));
        check("Failed host callback removes module action", menu.item()==null);
        invokeMenu(create,viewer,menu,null);
        prefs.fail = true; menu.item().click(); prefs.fail = false;
        check("Invalid preference type does not export",GalleryMediaExporter.exported.size()==1);

        // Inspect the compiled listener and clear its weak target without relying on GC timing.
        boolean weak = false;
        for (Field field : menu.item().listener.getClass().getDeclaredFields()) {
            field.setAccessible(true); Object value = field.get(menu.item().listener);
            check("Listener captures no fragment, Activity or menu",!(value instanceof Fragment)
                    && !(value instanceof android.app.Activity) && !(value instanceof Menu));
            if (value instanceof WeakReference<?>) { ((WeakReference<?>)value).clear(); weak = true; }
        }
        check("Listener owns a weak target", weak); menu.item().click(); idle();
        check("Collected viewer does not export",GalleryMediaExporter.exported.size()==1);

        invokeMenu(prepare,viewer,menu,null);
        GalleryMediaExporter.entered=new CountDownLatch(1);GalleryMediaExporter.release=new CountDownLatch(1);
        viewer.page.index=0;menu.item().click();
        check("Controlled export started",GalleryMediaExporter.entered.await(2,TimeUnit.SECONDS));
        for(int i=0;i<100;i++)menu.item().click();
        check("Rapid taps do not queue duplicate copies",worker().getQueue().isEmpty());
        check("Single worker",worker().getMaximumPoolSize()==1);
        GalleryMediaExporter.release.countDown();idle();
        check("Only one copy for rapid repeated taps",GalleryMediaExporter.exported.size()==2);
        GalleryMediaExporter.entered=null;GalleryMediaExporter.release=null;

        GalleryMediaExporter.fail=true;menu.item().click();idle();GalleryMediaExporter.fail=false;
        check("Copy error not recorded as success",GalleryMediaExporter.exported.size()==2);
        check("No path payload in logs",XposedBridge.logs.stream().noneMatch(x->x.contains("fixture-secret")||x.contains("/private")));
        check("No path payload in error toast",android.widget.Toast.shown.stream().noneMatch(x->x.contains("fixture-secret")||x.contains("/private")));
        menu.item().click();idle();check("Retry works after copy error",GalleryMediaExporter.exported.size()==3);

        // Queue without creating a worker, disable, then drain the actual production task.
        ThreadPoolExecutor executor=worker();
        executor.setKeepAliveTime(1,TimeUnit.MILLISECONDS);
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
        while(executor.getPoolSize()!=0&&System.nanoTime()<deadline)Thread.sleep(1);
        check("Worker idle before fault injection",executor.getPoolSize()==0);
        java.util.concurrent.ThreadFactory factory=executor.getThreadFactory();
        executor.setThreadFactory(r->null);
        menu.item().click();
        check("Accepted waiting export occupies only one slot",executor.getQueue().size()==1);
        prefs.enabled=false;executor.setThreadFactory(factory);executor.prestartCoreThread();idle();prefs.enabled=true;
        check("Queued export observes later disable",GalleryMediaExporter.exported.size()==3);

        // Worker count zero with core size zero executes the offer-then-start path.
        while(executor.getPoolSize()!=0&&System.nanoTime()<deadline)Thread.sleep(1);
        check("Worker idle for queued-then-failed submission",executor.getPoolSize()==0);
        executor.setCorePoolSize(0);
        executor.setThreadFactory(r->{throw new IllegalStateException("fixture worker start");});
        menu.item().click();
        check("Failed submission leaves an observable queued task",executor.getQueue().size()==1);
        check("Failed submission releases ticket",active().get()==null);
        Runnable abandoned=executor.getQueue().poll();
        executor.setThreadFactory(r->null);menu.item().click();
        check("New retry reserves its own ticket",active().get()!=null);
        Object retry=active().get();abandoned.run();
        check("Abandoned task cannot export or clear retry",GalleryMediaExporter.exported.size()==3&&active().get()==retry);
        executor.setThreadFactory(factory);executor.setCorePoolSize(1);executor.prestartCoreThread();idle();
        check("Only legitimate retry exports",GalleryMediaExporter.exported.size()==4);
        executor.shutdownNow();
        menu.item().click();check("Rejected executor releases reservation",active().get()==null);
    }
    static void baseline(String scenario) throws Throwable {
        DexSearchEngine.bridge=metadata();Prefs prefs=new Prefs();
        DownloadViewOnceHook hook=new DownloadViewOnceHook(APP,LOADER,prefs);
        File desired=file("desired"),decoy=file("wrong");
        Media message=media(desired,"chat@lid","message",false);
        if(scenario.equals("install")) {
            installationChecks();
        } else if(scenario.equals("lazy")) {
            Method extract=method(DownloadViewOnceHook.class,"extractFileFromFMessage",Object.class);extract.setAccessible(true);
            check("Canonical lazy media path must be resolved",desired.equals(extract.invoke(hook,message)));
        } else if(scenario.equals("decoy")) {
            message.unrelated=decoy;
            Method extract=method(DownloadViewOnceHook.class,"extractFileFromFMessage",Object.class);extract.setAccessible(true);
            check("Unrelated File must not replace canonical media",desired.equals(extract.invoke(hook,message)));
        } else if(scenario.equals("activity")) {
            com.whatsapp.viewonce.ui.messaging.ViewOnceViewerActivity activity=new com.whatsapp.viewonce.ui.messaging.ViewOnceViewerActivity();
            activity.unrelated=decoy;
            Method extract=method(DownloadViewOnceHook.class,"extractMediaFileFromActivity",android.app.Activity.class);extract.setAccessible(true);
            check("Activity without media identity cannot export a random file",extract.invoke(hook,activity)==null);
        } else if(scenario.equals("menu")) {
            hook.hook();MediaViewFragment viewer=viewer(message);MenuDouble menu=new MenuDouble();invokeMenu(create,viewer,menu,null);
            menu.item().click();
            long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            while(android.widget.Toast.shown.isEmpty()&&System.nanoTime()<end)Thread.sleep(1);
            check("Real MenuInflater/Menu callback must export current message",GalleryMediaExporter.exported.equals(List.of(desired)));
        } else throw new AssertionError("Unknown baseline scenario");
    }
    public static void main(String[] arguments) throws Throwable {
        if(arguments.length>1&&arguments[1].equals("baseline"))baseline(arguments[0]);
        else { resolverChecks();installationChecks();hookChecks(); }
        System.out.println("PASS: "+checks+" complete resolver, menu, identity and bounded export checks (explicit doubles)");
    }
}
