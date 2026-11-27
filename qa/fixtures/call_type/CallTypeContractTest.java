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
    public interface Calls4 { Jid getChatJid(); void voice(boolean a, boolean b, boolean c, boolean d); void video(boolean a, boolean b, boolean c, boolean d); }
    public interface MixedCalls { void voice(boolean a, boolean b, boolean c); void video(boolean a, boolean b, boolean c, boolean d); }
    public interface BadShapes {
        void twoA(boolean a, boolean b); void twoB(boolean a, boolean b);
        void fiveA(boolean a, boolean b, boolean c, boolean d, boolean e); void fiveB(boolean a, boolean b, boolean c, boolean d, boolean e);
        void boxedA(boolean a, boolean b, Boolean c); void boxedB(boolean a, boolean b, Boolean c);
        void integerA(boolean a, boolean b, int c); void integerB(boolean a, boolean b, int c);
    }
    public static class Conversation4 extends Conversation implements Calls4 {
        public void voice(boolean a, boolean b, boolean c, boolean d) {}
        public void video(boolean a, boolean b, boolean c, boolean d) {}
    }
    public static class InheritedConversation4 extends Conversation4 {}
    public static class NativeConversation4 extends Conversation4 {
        public native void voice(boolean a, boolean b, boolean c, boolean d);
        public void video(boolean a, boolean b, boolean c, boolean d) {}
    }
    public static class FragmentOwner4 extends FragmentOwner { public Adapter4 controller; }
    public static class AmbiguousOwner4 extends FragmentOwner { public Adapter4 first, second; }
    public static class Adapter4 extends Adapter implements Calls4 {
        public Adapter4(Context context) { super(context); }
        public void voice(boolean a, boolean b, boolean c, boolean d) {}
        public void video(boolean a, boolean b, boolean c, boolean d) {}
    }
    private static List<Method> calls4() throws Exception {
        return Arrays.asList(Calls4.class.getMethod("voice", boolean.class, boolean.class, boolean.class, boolean.class),
                Calls4.class.getMethod("video", boolean.class, boolean.class, boolean.class, boolean.class));
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
    @Test public void fourBooleanOperationsResolveWithoutDroppingAnArgument() throws Exception {
        CallTypeHostContract c = CallTypeHostContract.resolve(calls4(), Conversation4.class, FragmentOwner4.class, Jid.class);
        assertEquals(4, c.sites.size());
        for (int i = 0; i < c.sites.size(); i++) {
            Method method = c.sites.get(i).operation;
            assertEquals(i < 2 ? Conversation4.class : Adapter4.class, method.getDeclaringClass());
            assertArrayEquals(new Class<?>[]{boolean.class, boolean.class, boolean.class, boolean.class}, method.getParameterTypes());
        }
    }
    @Test public void mixedArgumentCountsFailClosedEvenOnTheSameInterface() throws Exception {
        List<Method> mixed = Arrays.asList(
                MixedCalls.class.getMethod("voice", boolean.class, boolean.class, boolean.class),
                MixedCalls.class.getMethod("video", boolean.class, boolean.class, boolean.class, boolean.class));
        try { CallTypeHostContract.resolve(mixed, Conversation4.class, FragmentOwner4.class, Jid.class); fail("mixed arities"); }
        catch (ReflectiveOperationException expected) {}
    }
    @Test public void unsupportedCountsAndNonBooleanArgumentsFailClosed() throws Exception {
        String[] names = {"two", "five", "boxed", "integer"};
        Class<?>[][] arguments = {{boolean.class, boolean.class},
                {boolean.class, boolean.class, boolean.class, boolean.class, boolean.class},
                {boolean.class, boolean.class, Boolean.class}, {boolean.class, boolean.class, int.class}};
        for (int i = 0; i < names.length; i++) {
            List<Method> calls = Arrays.asList(BadShapes.class.getMethod(names[i] + "A", arguments[i]),
                    BadShapes.class.getMethod(names[i] + "B", arguments[i]));
            try { CallTypeHostContract.resolve(calls, Conversation4.class, FragmentOwner4.class, Jid.class); fail(names[i]); }
            catch (ReflectiveOperationException expected) {}
        }
    }
    @Test public void fourArgumentOwnersRetainAmbiguityNativeAndDeclarationGuards() throws Exception {
        Class<?>[][] owners = {{Conversation4.class, AmbiguousOwner4.class},
                {NativeConversation4.class, FragmentOwner4.class}, {InheritedConversation4.class, FragmentOwner4.class}};
        for (Class<?>[] pair : owners) {
            try { CallTypeHostContract.resolve(calls4(), pair[0], pair[1], Jid.class); fail("unsupported owner"); }
            catch (ReflectiveOperationException expected) {}
        }
    }

}

