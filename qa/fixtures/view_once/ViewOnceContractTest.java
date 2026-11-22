import android.content.Context;
import android.content.SharedPreferences;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.features.privacy.AntiViewOnceHook;
import com.whatsapp.infra.core.jid.Jid;
import com.whatsapp.infra.core.jid.UserJid;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.result.*;
import java.lang.reflect.*;
import java.util.*;

public final class ViewOnceContractTest {
    private static int checks, failed;
    private static final Context CONTEXT = new Context();
    private static final ClassLoader LOADER = ViewOnceContractTest.class.getClassLoader();

    static final class Preferences implements SharedPreferences {
        final Map<String, Boolean> values = new HashMap<>();
        @Override public boolean getBoolean(String k, boolean fallback) { return values.getOrDefault(k, fallback); }
        void put(String k, boolean enabled) { values.put(k, enabled); }
    }
    public interface ViewState { int getState(); void setState(int value); }
    public interface AmbiguousState { int getState(); void first(int value); void second(int value); }
    public static final class Key {
        final String id;
        final boolean fromMe;
        final Jid chat;
        Key(boolean own) { id = "fixture-id"; fromMe = own; chat = new Jid(); }
    }
    public static class Message {
        final Key primary;
        Key mutableDecoy;
        final Key otherFinal;
        Message(Key key) { primary = key; mutableDecoy = new Key(true); otherFinal = new Key(true); }
        public UserJid sender() { return new UserJid(); }
    }
    public static class Photo extends Message implements ViewState {
        int state = -1, unrelated = -1;
        Photo(Key key) { super(key); }
        public int getState() { return state; }
        public void setState(int value) { state = value; }
        public void setUnrelated(int value) { unrelated = value; }
    }
    public static class InheritedPhoto extends Photo { InheritedPhoto(Key key) { super(key); } }
    public static class Video extends Message implements ViewState {
        int state = -1;
        Video(Key key) { super(key); }
        public int getState() { return state; }
        public void setState(int value) { state = value; }
    }
    public static class NotMessage implements ViewState {
        int state = -1;
        public int getState() { return state; }
        public void setState(int value) { state = value; }
    }
    public static class AmbiguousPhoto extends Message implements AmbiguousState {
        AmbiguousPhoto(Key key) { super(key); }
        public int getState() { return 1; }
        public void first(int value) {}
        public void second(int value) {}
    }
    public static class DirectPhoto extends Message {
        int state = -1;
        DirectPhoto(Key key) { super(key); }
        public void directState(int value) { state = value; }
        public void otherDirectState(int value) { state = value; }
        public static void staticState(int value) {}
    }
    public static class Sql {
        public void unrelated() {}
        public void savePhoto() {}
        public void saveVideo() {}
    }
    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) { failed++; System.out.println("FAIL " + label); }
    }
    private static void expectUnavailable(BaseFeature hook, String label) {
        Throwable failure = null;
        try { hook.hook(); } catch (Throwable unavailable) { failure = unavailable; }
        check(failure instanceof IllegalStateException, label + "/missing contract is reported");
        check(failure != null && "View-once contract unavailable".equals(failure.getMessage()),
                label + "/unavailable diagnostic is generic");
    }
    private static Method method(Class<?> c, String name, Class<?>... args) throws Exception {
        return c.getMethod(name, args);
    }
    private static MethodData metadata(DexKitBridge b, Class<?> c, String name, String anchor, Class<?>... args)
            throws Exception {
        MethodData value = new MethodData(method(c, name, args), anchor);
        b.methods.add(value);
        return value;
    }
    private static DexKitBridge reset() {
        XposedBridge.hooks.clear(); XposedBridge.logs.clear(); XposedBridge.rejected.clear();
        DexSearchEngine.initializes = 0; DexSearchEngine.failure = null;
        DexKitBridge b = new DexKitBridge(); DexSearchEngine.bridge = b; return b;
    }
    private static void identity(DexKitBridge b, boolean ambiguous) throws Exception {
        MethodData sender = metadata(b, Message.class, "sender", "FMessage/getSenderUserJid/key.id=");
        sender.fields.add(new UsingFieldData(Message.class.getDeclaredField("primary")));
        sender.fields.add(new UsingFieldData(Message.class.getDeclaredField("mutableDecoy")));
        if (ambiguous) sender.fields.add(new UsingFieldData(Message.class.getDeclaredField("otherFinal")));
    }
    private static DexKitBridge viewFixture(boolean decoyFirst, boolean ambiguousKey) throws Exception {
        DexKitBridge b = reset(); identity(b, ambiguousKey);
        if (decoyFirst) metadata(b, Sql.class, "unrelated", "INSERT_VIEW_ONCE_SQL");
        MethodData caller = metadata(b, Sql.class, "savePhoto", "INSERT_VIEW_ONCE_SQL");
        // Storage reads state: the setter is the other method in this exact interface.
        caller.invokes.add(new MethodData(method(ViewState.class, "getState")));
        caller.invokes.add(new MethodData(method(ViewState.class, "getState")));
        MethodData second = metadata(b, Sql.class, "saveVideo", "INSERT_VIEW_ONCE_SQL");
        second.invokes.add(new MethodData(method(ViewState.class, "getState")));
        for (Class<?> type : new Class<?>[]{Photo.class, Video.class, NotMessage.class,
                                          InheritedPhoto.class, Photo.class}) {
            b.classes.add(new ClassData(type));
        }
        return b;
    }
    private static void setState(Object target, int input) throws Throwable {
        XposedBridge.invoke(method(target.getClass(), "setState", int.class), target, input);
    }
    private static void viewOnceTests() throws Throwable {
        Preferences p = new Preferences(); p.put("anti_view_once", true);
        DexKitBridge b = viewFixture(false, false);
        AntiViewOnceHook hook = new AntiViewOnceHook(CONTEXT, LOADER, p); hook.hook();
        Photo incoming = new Photo(new Key(false)); setState(incoming, 1);
        check(incoming.state == 0, "viewonce/incoming state 1 becomes standard");
        Photo outgoing = new Photo(new Key(true)); setState(outgoing, 1);
        check(outgoing.state == 1, "viewonce/outgoing media remains view-once");
        Photo unknown = new Photo(null); setState(unknown, 1);
        check(unknown.state == 1, "viewonce/missing identity preserves host state");
        NotMessage unrelated = new NotMessage(); setState(unrelated, 1);
        check(unrelated.state == 1, "viewonce/non-message implementor untouched");
        XposedBridge.invoke(method(Photo.class, "setUnrelated", int.class), incoming, 1);
        check(incoming.unrelated == 1, "viewonce/unrelated integer setter untouched");
        check(XposedBridge.registrations() == 2, "viewonce/exactly two concrete setters, no duplicate hooks");
        System.out.println("METRIC viewonce initial_queries=" + b.queries
                + " initial_registrations=" + XposedBridge.registrations()
                + " callbacks_per_photo_set=" + XposedBridge.hooks.getOrDefault(
                        method(Photo.class, "setState", int.class), Collections.emptyList()).size());
        int installed = XposedBridge.registrations(); hook.hook();
        check(XposedBridge.registrations() == installed, "viewonce/repeated installation is idempotent");
        for (int value : new int[]{-1, 0, 2, Integer.MAX_VALUE}) {
            setState(incoming, value); check(incoming.state == value, "viewonce/preserve state " + value);
        }
        InheritedPhoto inherited = new InheritedPhoto(new Key(false)); setState(inherited, 1);
        check(inherited.state == 0, "viewonce/inherited concrete setter works");
        p.put("anti_view_once", false); setState(incoming, 1);
        check(incoming.state == 1, "viewonce/live disable");
        p.put("viewonce", true); setState(incoming, 1);
        check(incoming.state == 0, "viewonce/legacy live enable");
        int scans = b.queries;
        for (int i = 0; i < 500; i++) setState(incoming, 1);
        check(b.queries == scans, "viewonce/no DexKit scan from callbacks");

        viewFixture(true, false); new AntiViewOnceHook(CONTEXT, LOADER, p).hook();
        Photo later = new Photo(new Key(false)); setState(later, 1);
        check(later.state == 0, "viewonce/valid SQL caller after unrelated first result");

        viewFixture(false, true);
        expectUnavailable(new AntiViewOnceHook(CONTEXT, LOADER, p), "viewonce/ambiguous immutable message key");
        check(XposedBridge.hooks.isEmpty(), "viewonce/ambiguous immutable message key fails open");

        b = reset(); identity(b, false);
        MethodData caller = metadata(b, Sql.class, "savePhoto", "INSERT_VIEW_ONCE_SQL");
        caller.invokes.add(new MethodData(method(AmbiguousState.class, "getState")));
        b.classes.add(new ClassData(AmbiguousPhoto.class));
        expectUnavailable(new AntiViewOnceHook(CONTEXT, LOADER, p), "viewonce/ambiguous state interface");
        check(XposedBridge.hooks.isEmpty(), "viewonce/ambiguous state interface fails open");

        b = reset(); identity(b, false);
        metadata(b, DirectPhoto.class, "directState", "view_once", int.class);
        metadata(b, DirectPhoto.class, "staticState", "view_once", int.class);
        metadata(b, NotMessage.class, "setState", "view_once", int.class);
        new AntiViewOnceHook(CONTEXT, LOADER, p).hook();
        check(XposedBridge.registrations() == 1, "viewonce/direct fallback only concrete message setter");
        DirectPhoto direct = new DirectPhoto(new Key(false));
        XposedBridge.invoke(method(DirectPhoto.class, "directState", int.class), direct, 1);
        check(direct.state == 0, "viewonce/direct fallback incoming state");
        direct = new DirectPhoto(new Key(true));
        XposedBridge.invoke(method(DirectPhoto.class, "directState", int.class), direct, 1);
        check(direct.state == 1, "viewonce/direct fallback outgoing state");

        b = reset(); identity(b, false);
        metadata(b, DirectPhoto.class, "directState", "view_once", int.class);
        metadata(b, DirectPhoto.class, "otherDirectState", "view_once", int.class);
        expectUnavailable(new AntiViewOnceHook(CONTEXT, LOADER, p), "viewonce/ambiguous direct setters");
        check(XposedBridge.hooks.isEmpty(), "viewonce/ambiguous direct setters fail open");

        b = viewFixture(false, false); Preferences initiallyOff = new Preferences();
        new AntiViewOnceHook(CONTEXT, LOADER, initiallyOff).hook();
        initiallyOff.put("anti_view_once", true); Photo live = new Photo(new Key(false)); setState(live, 1);
        check(live.state == 0, "viewonce/install while off keeps existing live-enable contract");
    }

    public static final class NarrowJid extends Jid {}
    public static final class NarrowKey {
        final String id="fixture-narrow";final boolean fromMe;final NarrowJid chat=new NarrowJid();
        NarrowKey(boolean own){fromMe=own;}
    }
    public static class NarrowMessage {
        public final NarrowKey primary;public final NarrowKey secondary=new NarrowKey(true);
        public NarrowMessage(NarrowKey key){primary=key;}
        public UserJid sender(){return new UserJid();}
    }
    public static final class NarrowPhoto extends NarrowMessage implements ViewState {
        public int state=1;NarrowPhoto(NarrowKey key){super(key);}
        public int getState(){return state;}public void setState(int value){state=value;}
    }
    private static void jidSubtypeTests()throws Throwable {
        Preferences prefs=new Preferences();prefs.put("anti_view_once",true);
        for(boolean ambiguous:new boolean[]{false,true}){
            DexKitBridge b=reset();
            MethodData sender=metadata(b,NarrowMessage.class,"sender","FMessage/getSenderUserJid/key.id=");
            sender.fields.add(new UsingFieldData(NarrowMessage.class.getDeclaredField("primary")));
            if(ambiguous)sender.fields.add(new UsingFieldData(NarrowMessage.class.getDeclaredField("secondary")));
            MethodData sql=metadata(b,Sql.class,"savePhoto","INSERT_VIEW_ONCE_SQL");
            sql.invokes.add(new MethodData(method(ViewState.class,"getState")));
            b.classes.add(new ClassData(NarrowPhoto.class));
            if(ambiguous){
                expectUnavailable(new AntiViewOnceHook(CONTEXT,LOADER,prefs),"viewonce/subtype ambiguous keys");
                check(XposedBridge.registrations()==0,"viewonce/ambiguous subtype no callbacks");continue;
            }
            boolean installed=true;
            try {new AntiViewOnceHook(CONTEXT,LOADER,prefs).hook();} catch(IllegalStateException unavailable){installed=false;}
            check(installed,"viewonce/subclass Jid discovery completes");
            check(XposedBridge.registrations()==1,"viewonce/subclass Jid accepted with exact verified base");
            NarrowPhoto incoming=new NarrowPhoto(new NarrowKey(false));
            XposedBridge.invoke(method(NarrowPhoto.class,"setState",int.class),incoming,1);
            check(incoming.state==0,"viewonce/subtype incoming state changed");
            NarrowPhoto outgoing=new NarrowPhoto(new NarrowKey(true));
            XposedBridge.invoke(method(NarrowPhoto.class,"setState",int.class),outgoing,1);
            check(outgoing.state==1,"viewonce/subtype outgoing preserved");
            NarrowPhoto unknown=new NarrowPhoto(null);
            XposedBridge.invoke(method(NarrowPhoto.class,"setState",int.class),unknown,1);
            check(unknown.state==1,"viewonce/subtype null key preserved");
            XposedBridge.invoke(method(NarrowPhoto.class,"setState",int.class),incoming,2);
            check(incoming.state==2,"viewonce/subtype unrelated state preserved");
        }
    }
    public static void main(String[] args) throws Throwable {
        viewOnceTests();
        jidSubtypeTests();
        System.out.println("RESULT checks=" + checks + " failures=" + failed + " suite=viewonce");
        if (failed != 0) throw new AssertionError(failed + " view-once contract failures");
        System.out.println("PASS compiled production view-once hooks and explicit host/Xposed boundaries");
    }
}
