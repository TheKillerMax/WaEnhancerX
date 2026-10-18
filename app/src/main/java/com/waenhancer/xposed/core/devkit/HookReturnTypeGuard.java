package com.waenhancer.xposed.core.devkit;

import java.lang.reflect.Method;

/**
 * Prevents an Xposed callback from writing a result or positional argument with
 * an incompatible type into an obfuscated host method. Not a semantic guarantee:
 * call sites still need to identify the *correct* method, not merely a compatible type.
 */
public final class HookReturnTypeGuard {
    private HookReturnTypeGuard() {}

    public static boolean returnsInteger(Method method) {
        return method != null
                && (method.getReturnType() == int.class
                        || method.getReturnType() == Integer.class);
    }

    public static boolean returnsBoolean(Method method) {
        return method != null
                && (method.getReturnType() == boolean.class
                        || method.getReturnType() == Boolean.class);
    }

    public static boolean firstParameterIsInteger(Method method) {
        if (method == null) return false;
        Class<?>[] parameterTypes = method.getParameterTypes();
        return parameterTypes.length > 0
                && (parameterTypes[0] == int.class || parameterTypes[0] == Integer.class);
    }
}
