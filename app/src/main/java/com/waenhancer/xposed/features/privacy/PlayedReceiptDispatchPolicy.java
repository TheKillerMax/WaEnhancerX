package com.waenhancer.xposed.features.privacy;

import java.lang.reflect.Member;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Set;

/** Shape validation complements, but never replaces, the verified DEX call edge. */
public final class PlayedReceiptDispatchPolicy {
    private PlayedReceiptDispatchPolicy() {}

    public static boolean isDispatchMethod(Method method) {
        if (method == null) return false;
        int flags = method.getModifiers();
        Class<?>[] parameters = method.getParameterTypes();
        return Modifier.isPublic(flags) && !Modifier.isStatic(flags)
                && !Modifier.isAbstract(flags) && !Modifier.isNative(flags)
                && !method.isBridge() && !method.isSynthetic()
                && method.getReturnType() == void.class && parameters.length == 2
                && parameters[0] == Set.class && parameters[1] == boolean.class;
    }

    public static boolean isDispatchCall(Method selected, Member called,
            Object receiver, Object[] arguments) {
        return isDispatchMethod(selected) && selected.equals(called)
                && selected.getDeclaringClass().isInstance(receiver)
                && arguments != null && arguments.length == 2
                && arguments[0] instanceof Set && arguments[1] instanceof Boolean;
    }
}
