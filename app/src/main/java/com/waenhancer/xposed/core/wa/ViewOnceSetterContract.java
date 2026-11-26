package com.waenhancer.xposed.core.wa;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.LinkedHashSet;

/** Resolves the exact state setter read by the SQL caller, never every (int)void method. */
final class ViewOnceSetterContract {
    private ViewOnceSetterContract() {}

    static Method interfaceSetter(Method invoked) {
        if (invoked == null || !invoked.getDeclaringClass().isInterface()) return null;
        Method getter = null, setter = null;
        for (Method method : invoked.getDeclaringClass().getMethods()) {
            if (Modifier.isStatic(method.getModifiers()) || method.isBridge() || method.isSynthetic()) continue;
            Class<?>[] parameters = method.getParameterTypes();
            if (method.getReturnType() == int.class && parameters.length == 0) {
                if (getter != null && !getter.equals(method)) return null;
                getter = method;
            } else if (method.getReturnType() == void.class && parameters.length == 1
                    && parameters[0] == int.class) {
                if (setter != null && !setter.equals(method)) return null;
                setter = method;
            } else {
                return null;
            }
        }
        return getter != null && setter != null && (invoked.equals(getter) || invoked.equals(setter))
                ? setter : null;
    }

    static Method uniqueSetter(Iterable<Method> invocations) {
        Method selected = null;
        for (Method invocation : invocations) {
            Method candidate = interfaceSetter(invocation);
            if (candidate == null) continue;
            if (selected != null && !selected.equals(candidate)) return null;
            selected = candidate;
        }
        return selected;
    }

    static Method[] implementations(Method setter, Class<?> messageClass, Iterable<Class<?>> candidates)
            throws ReflectiveOperationException {
        if (setter == null || messageClass == null || !setter.equals(interfaceSetter(setter))) return null;
        LinkedHashSet<Method> methods = new LinkedHashSet<>();
        for (Class<?> candidate : candidates) {
            if (candidate == null || !messageClass.isAssignableFrom(candidate)
                    || !setter.getDeclaringClass().isAssignableFrom(candidate)) continue;
            // getMethod preserves the interface member name and supports an inherited implementation.
            Method implementation = candidate.getMethod(setter.getName(), int.class);
            // A generic superclass outside this interface could serve unrelated messages.
            if (!setter.getDeclaringClass().isAssignableFrom(implementation.getDeclaringClass())) continue;
            if (isMessageSetter(implementation, messageClass)) methods.add(implementation);
        }
        return methods.isEmpty() ? null : methods.toArray(new Method[0]);
    }

    static Method[] cacheEntry(Method setter, Class<?> messageClass, Iterable<Class<?>> candidates)
            throws ReflectiveOperationException {
        Method[] methods = implementations(setter, messageClass, candidates);
        if (methods == null) return null;
        Method[] entry = new Method[methods.length + 1];
        entry[0] = setter;
        System.arraycopy(methods, 0, entry, 1, methods.length);
        return entry;
    }

    /** Cache the interface contract as metadata; it is never returned for hooking. */
    static Method[] validatedCached(Method[] entry, Class<?> messageClass) {
        if (entry == null || entry.length < 2 || messageClass == null) return null;
        Method setter = entry[0];
        if (setter == null || !setter.equals(interfaceSetter(setter))) return null;
        LinkedHashSet<Method> unique = new LinkedHashSet<>();
        for (int index = 1; index < entry.length; index++) {
            Method method = entry[index];
            if (!isMessageSetter(method, messageClass) || !unique.add(method)
                    || !setter.getName().equals(method.getName())
                    || !setter.getDeclaringClass().isAssignableFrom(method.getDeclaringClass())) return null;
        }
        return Arrays.copyOfRange(entry, 1, entry.length);
    }

    private static boolean isMessageSetter(Method method, Class<?> messageClass) {
        if (method == null) return false;
        int flags = method.getModifiers();
        return messageClass.isAssignableFrom(method.getDeclaringClass())
                && Modifier.isPublic(flags) && !Modifier.isStatic(flags) && !Modifier.isAbstract(flags)
                && !Modifier.isNative(flags) && !method.isBridge() && !method.isSynthetic()
                && method.getReturnType() == void.class && method.getParameterTypes().length == 1
                && method.getParameterTypes()[0] == int.class;
    }
}
