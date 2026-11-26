package com.waenhancer.xposed.core.wa;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Collections;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;

public final class ViewOnceSetterContractChecks {
    public interface State { int read(); void write(int value); }
    public interface OtherState { int readOther(); void writeOther(int value); }
    public interface TooWide { int read(); void write(int value); void extra(); }
    public interface TwoSetters { int read(); void first(int value); void second(int value); }
    public interface WrongType { boolean read(); void write(int value); }
    public interface StaticExtras extends State { static void unrelated(int value) {} }
    public static class Message { public void unrelated(int value) {} }
    public static class Incoming extends Message implements State {
        public int read() { return 1; }
        public void write(int value) {}
        public void unrelated(int value) {}
    }
    public static class Inherited extends Incoming {}
    public static class GenericOwner extends Message { public void write(int value) {} }
    public static class InheritedOutsideContract extends GenericOwner implements State {
        public int read() { return 1; }
    }
    public static class Foreign implements State {
        public int read() { return 1; }
        public void write(int value) {}
    }
    public abstract static class Unimplemented extends Message implements State {}
    public static class StaticMessage extends Message { public static void staticWrite(int value) {} }
    public static class NativeMessage extends Message implements State {
        public int read() { return 1; }
        public native void write(int value);
    }
    private static int checks, failures;
    private static void check(String label, boolean value) {
        checks++; if (!value) { failures++; System.err.println("ASSERTION: " + label); }
    }
    private static Method method(Class<?> type, String name, Class<?>... parameters) throws Exception {
        return type.getMethod(name, parameters);
    }
    private static void rejectsCache(Method[] values, String label) throws Exception {
        DexSearchEngine.cachedMethods = values;
        boolean rejected = false;
        try { WaTargets.viewOnceSetters(null, ViewOnceSetterContractChecks.class.getClassLoader()); }
        catch (NoSuchMethodException expected) { rejected = true; }
        check(label, rejected);
    }
    public static void main(String[] args) throws Exception {
        Method getter = method(State.class, "read"), setter = method(State.class, "write", int.class);
        check("getter resolves exact setter", setter.equals(ViewOnceSetterContract.interfaceSetter(getter)));
        check("setter invocation resolves itself", setter.equals(ViewOnceSetterContract.interfaceSetter(setter)));
        check("null rejected", ViewOnceSetterContract.interfaceSetter(null) == null);
        check("concrete method is not an interface contract", ViewOnceSetterContract.interfaceSetter(method(Incoming.class,"read")) == null);
        check("wider interface rejected", ViewOnceSetterContract.interfaceSetter(method(TooWide.class,"read")) == null);
        check("two state setters rejected", ViewOnceSetterContract.interfaceSetter(method(TwoSetters.class,"read")) == null);
        check("wrong getter type rejected", ViewOnceSetterContract.interfaceSetter(method(WrongType.class,"read")) == null);
        check("inherited contract remains exact", setter.equals(ViewOnceSetterContract.interfaceSetter(method(StaticExtras.class,"read"))));
        check("repeated calls deduplicate", setter.equals(ViewOnceSetterContract.uniqueSetter(Arrays.asList(getter,setter,getter))));
        check("empty invocations unavailable", ViewOnceSetterContract.uniqueSetter(Collections.emptyList()) == null);
        check("two distinct state contracts are ambiguous", ViewOnceSetterContract.uniqueSetter(Arrays.asList(getter,method(OtherState.class,"readOther"))) == null);
        Method[] selected = ViewOnceSetterContract.implementations(setter, Message.class,
                Arrays.asList(Incoming.class, Inherited.class, Foreign.class, Unimplemented.class));
        check("only one exact implementation", selected != null && selected.length == 1);
        check("unrelated int setter never hooked", selected != null && Arrays.equals(selected,new Method[]{method(Incoming.class,"write",int.class)}));
        check("foreign type alone unavailable", ViewOnceSetterContract.implementations(setter,Message.class,Arrays.asList(Foreign.class)) == null);
        check("unresolved message class unavailable", ViewOnceSetterContract.implementations(setter,null,Arrays.asList(Incoming.class)) == null);
        check("abstract implementation unavailable", ViewOnceSetterContract.implementations(setter,Message.class,Arrays.asList(Unimplemented.class)) == null);
        check("unknown setter unavailable", ViewOnceSetterContract.implementations(null,Message.class,Arrays.asList(Incoming.class)) == null);
        check("generic inherited owner outside the interface is unavailable", ViewOnceSetterContract.implementations(setter,Message.class,Arrays.asList(InheritedOutsideContract.class)) == null);
        check("generic inherited owner cannot enter through cache", ViewOnceSetterContract.validatedCached(new Method[]{setter,method(GenericOwner.class,"write",int.class)},Message.class) == null);
        Method[] packed = ViewOnceSetterContract.cacheEntry(setter,Message.class,Arrays.asList(Incoming.class,Inherited.class));
        check("cache stores interface metadata", packed.length == 2 && packed[0].equals(setter));
        check("cache metadata never returned for hooking", Arrays.equals(selected,ViewOnceSetterContract.validatedCached(packed,Message.class)));
        check("missing cache header rejected", ViewOnceSetterContract.validatedCached(selected,Message.class) == null);
        check("getter cannot stand in for setter header", ViewOnceSetterContract.validatedCached(new Method[]{getter,selected[0]},Message.class) == null);
        check("unrelated named int method rejected from cache", ViewOnceSetterContract.validatedCached(new Method[]{setter,method(Incoming.class,"unrelated",int.class)},Message.class) == null);
        check("wrong state interface header rejected", ViewOnceSetterContract.validatedCached(new Method[]{method(OtherState.class,"writeOther",int.class),selected[0]},Message.class) == null);
        check("duplicate cache rejected", ViewOnceSetterContract.validatedCached(new Method[]{setter,selected[0],selected[0]},Message.class) == null);
        check("static cache rejected", ViewOnceSetterContract.validatedCached(new Method[]{setter,method(StaticMessage.class,"staticWrite",int.class)},Message.class) == null);
        check("native cache rejected", ViewOnceSetterContract.validatedCached(new Method[]{setter,method(NativeMessage.class,"write",int.class)},Message.class) == null);
        check("foreign cache rejected", ViewOnceSetterContract.validatedCached(new Method[]{setter,method(Foreign.class,"write",int.class)},Message.class) == null);
        DexSearchEngine.messageClass = Message.class;
        DexSearchEngine.cachedMethods = new Method[]{setter,method(Incoming.class,"write",int.class)};
        Method[] cached = WaTargets.viewOnceSetters(null, ViewOnceSetterContractChecks.class.getClassLoader());
        check("real WaTargets returns validated cache", Arrays.equals(cached,new Method[]{DexSearchEngine.cachedMethods[1]}));
        check("old broad selector cache retired", "waex_wa_view_once_setters_v3".equals(DexSearchEngine.lastCacheKey));
        rejectsCache(null,"real WaTargets rejects missing cache");
        rejectsCache(new Method[0],"real WaTargets rejects empty cache");
        rejectsCache(new Method[]{setter,method(Foreign.class,"write",int.class)},"real WaTargets rejects foreign cache");
        rejectsCache(new Method[]{setter,method(StaticMessage.class,"staticWrite",int.class)},"real WaTargets rejects static cache");
        rejectsCache(new Method[]{setter,method(NativeMessage.class,"write",int.class)},"real WaTargets rejects native cache with the correct name and interface");
        rejectsCache(new Method[]{setter,method(Incoming.class,"unrelated",int.class)},"real WaTargets rejects unrelated member of the correct message type");
        DexSearchEngine.messageClass = null;
        rejectsCache(new Method[]{setter,method(Incoming.class,"write",int.class)},"real WaTargets rejects unresolved message type");
        System.out.println("CHECKS=" + checks + " FAILURES=" + failures);
        if (failures != 0) throw new AssertionError("View-once setter contract failures=" + failures);
    }
}
