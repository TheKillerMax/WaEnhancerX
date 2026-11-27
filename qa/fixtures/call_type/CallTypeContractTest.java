package com.waenhancer.xposed.features.privacy;

import android.app.Activity;
import android.content.Context;
import android.view.View;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

/** Reflection and live-owner contract only; no menu discovery, Xposed or external calls. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class CallTypeContractTest {
    public enum State { DESTROYED, INITIALIZED, CREATED, STARTED, RESUMED }
    public static class Lifecycle { public State state = State.RESUMED; public State current() { return state; } }
    public static class AmbiguousLifecycle extends Lifecycle { public State duplicate() { return state; } }
    public static class Jid { final String value; Jid(String value) { this.value = value; } public String getRawString() { return value; } }
    public interface Calls { Jid getChatJid(); void voice(boolean a, boolean b, boolean c); void video(boolean a, boolean b, boolean c); }
    public interface OtherCalls { void voice(boolean a, boolean b, boolean c); }
    public static class Conversation extends Activity implements Calls {
        public Jid jid = new Jid("15551234567@s.whatsapp.net");
        public Lifecycle life = new Lifecycle();
        public Jid getChatJid() { return jid; }
        public Lifecycle getLifecycle() { return life; }
        public void voice(boolean a, boolean b, boolean c) {}
        public void video(boolean a, boolean b, boolean c) {}
    }
    public static class FragmentOwner { public Adapter adapter; }
    public static class AmbiguousOwner { public Adapter first, second; }
    public static class Adapter extends View implements Calls {
        public Adapter(Context context) { super(context); }
        public Jid getChatJid() { return null; }
        public Lifecycle getLifecycle() { return new Lifecycle(); }
        public Activity getActivityNullable() { return (Activity) getContext(); }
        public FragmentOwner getHost() { return null; }
        public void voice(boolean a, boolean b, boolean c) {}
        public void video(boolean a, boolean b, boolean c) {}
    }
    public static class NativeConversation extends Conversation {
        public native void voice(boolean a, boolean b, boolean c);
        public void video(boolean a, boolean b, boolean c) {}
    }
    public static class AmbiguousStateConversation extends Conversation {
        public AmbiguousLifecycle getLifecycle() { return new AmbiguousLifecycle(); }
        public void voice(boolean a, boolean b, boolean c) {}
        public void video(boolean a, boolean b, boolean c) {}
    }
    private ActivityController<Conversation> controller;
    @After public void cleanup() { if (controller != null) controller.pause().stop().destroy(); }
    private static List<Method> calls() throws Exception {
        return Arrays.asList(Calls.class.getMethod("voice", boolean.class, boolean.class, boolean.class),
                Calls.class.getMethod("video", boolean.class, boolean.class, boolean.class));
    }
    private static CallTypeHostContract resolve(Class<?> activity, Class<?> fragment) throws Exception {
        return CallTypeHostContract.resolve(calls(), activity, fragment, Jid.class);
    }
    private Conversation activity() {
        controller = Robolectric.buildActivity(Conversation.class).create().start().resume().visible();
        return controller.get();
    }
    private static void rejected(Class<?> activity, Class<?> fragment) throws Exception {
        try { resolve(activity, fragment); fail("unsupported or ambiguous host must be rejected"); }
        catch (ReflectiveOperationException expected) {}
    }
    @Test public void resolvesExactlyFourConcreteOperations() throws Exception {
        CallTypeHostContract c = resolve(Conversation.class, FragmentOwner.class);
        assertEquals(4, c.sites.size());
        assertEquals(Conversation.class, c.sites.get(0).operation.getDeclaringClass());
        assertEquals(Adapter.class, c.sites.get(3).operation.getDeclaringClass());
        try { c.sites.clear(); fail("contract inventory must be immutable"); }
        catch (UnsupportedOperationException expected) {}
    }
    @Test public void snapshotsReadTheCurrentPnAndLidFromTheOwner() throws Exception {
        Conversation a = activity();
        CallTypeHostContract.Site site = resolve(Conversation.class, FragmentOwner.class).sites.get(0);
        assertSame(a, site.read(a).activity);
        assertEquals("15551234567@s.whatsapp.net", site.read(a).peer);
        a.jid = new Jid("9876543210@lid");
        assertEquals("9876543210@lid", site.read(a).peer);
    }
    @Test public void unsupportedOrMissingPeerCannotProduceASnapshot() throws Exception {
        Conversation a = activity();
        CallTypeHostContract.Site site = resolve(Conversation.class, FragmentOwner.class).sites.get(0);
        for (String peer : new String[]{"12345@g.us", "status@broadcast", "12345", "12345@lid.evil"}) {
            a.jid = new Jid(peer); assertNull(site.read(a));
        }
        a.jid = null; assertNull(site.read(a));
        assertNull(site.read(new Object()));
    }
    @Test public void nonResumedOwnerCannotProduceASnapshot() throws Exception {
        Conversation a = activity();
        CallTypeHostContract.Site site = resolve(Conversation.class, FragmentOwner.class).sites.get(0);
        for (State state : State.values()) {
            a.life.state = state;
            assertEquals(state == State.RESUMED, site.read(a) != null);
        }
    }
    @Test public void multipleFragmentAdaptersFailClosed() throws Exception {
        rejected(Conversation.class, AmbiguousOwner.class);
    }
    @Test public void mixedConversationInterfacesFailClosed() throws Exception {
        List<Method> mixed = calls();
        mixed.set(0, OtherCalls.class.getMethod("voice", boolean.class, boolean.class, boolean.class));
        try { CallTypeHostContract.resolve(mixed, Conversation.class, FragmentOwner.class, Jid.class); fail("mixed APIs"); }
        catch (ReflectiveOperationException expected) {}
    }
    @Test public void nativeOperationsFailClosed() throws Exception {
        rejected(NativeConversation.class, FragmentOwner.class);
    }
    @Test public void ambiguousLifecycleStateFailsClosed() throws Exception {
        rejected(AmbiguousStateConversation.class, FragmentOwner.class);
    }
}
