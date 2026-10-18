package com.waenhancer.xposed.features.privacy;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.HashSet;
import java.util.Set;

/** Narrow status revoke/playback contracts independent of obfuscated member names. */
public final class StatusHookContract {
    private final Class<?> keyClass;
    private final Field idField;
    private final Field fromMeField;
    private final Object acknowledgement;

    private StatusHookContract(Class<?> keyClass, Field idField, Field fromMeField,
                               Object acknowledgement) {
        this.keyClass = keyClass;
        this.idField = idField;
        this.fromMeField = fromMeField;
        this.acknowledgement = acknowledgement;
    }

    /**
     * The inspected receiver contract is (revokeKey, targetKey, incoming) -> store result.
     * Its callers require a non-null enum and treat STORED as successful consumption,
     * including cleanup of a pending revoke. A preserved revoke is acknowledged with
     * that native constant; no host status deletion or replacement is performed.
     */
    public static StatusHookContract resolveRevoke(Method method, Class<?> keyClass) {
        if (!isConcreteInstanceMethod(method) || keyClass == null) return null;
        Class<?>[] parameters = method.getParameterTypes();
        if (parameters.length != 3 || parameters[0] != keyClass
                || parameters[1] != keyClass || parameters[2] != boolean.class) return null;

        Object acknowledgement = storedAcknowledgement(method.getReturnType());
        if (acknowledgement == null) return null;
        Field id = uniqueInstanceField(keyClass, String.class);
        Field fromMe = uniqueInstanceField(keyClass, boolean.class);
        if (id == null || fromMe == null) return null;
        try {
            id.setAccessible(true);
            fromMe.setAccessible(true);
            return new StatusHookContract(keyClass, id, fromMe, acknowledgement);
        } catch (RuntimeException inaccessible) {
            return null;
        }
    }

    public static boolean supportsKeyClass(Class<?> keyClass) {
        return keyClass != null && uniqueInstanceField(keyClass, String.class) != null
                && uniqueInstanceField(keyClass, boolean.class) != null;
    }

    public static Method selectRevokeMethod(Iterable<Method> candidates, Class<?> keyClass) {
        Method selected = null;
        for (Method candidate : candidates) {
            if (resolveRevoke(candidate, keyClass) == null) continue;
            if (selected != null && !selected.equals(candidate)) return null;
            selected = candidate;
        }
        return selected;
    }

    /** Invalid, local, self-owned, or ambiguous calls retain the host's normal path. */
    public Target incomingTarget(Object[] args) {
        if (args == null || args.length != 3 || !Boolean.TRUE.equals(args[2])
                || (args[0] != null && !keyClass.isInstance(args[0]))
                || !keyClass.isInstance(args[1])) return null;
        try {
            Object key = args[1];
            if (fromMeField.getBoolean(key)) return null;
            String id = (String) idField.get(key);
            if (id == null || id.isEmpty()) return null;
            return new Target(key, id);
        } catch (IllegalAccessException | IllegalArgumentException inaccessible) {
            return null;
        }
    }

    public Object acknowledgement() {
        return acknowledgement;
    }

    public static final class Target {
        public final Object key;
        public final String id;

        private Target(Object key, String id) {
            this.key = key;
            this.id = id;
        }
    }

    public static boolean isStatusMapper(Method method, Class<?> messageClass) {
        if (!isConcreteInstanceMethod(method) || messageClass == null) return false;
        Class<?>[] parameters = method.getParameterTypes();
        return parameters.length == 1 && !parameters[0].isPrimitive()
                && parameters[0] != Object.class
                && messageClass.isAssignableFrom(method.getReturnType());
    }

    public static Method selectStatusMapper(Iterable<Method> candidates, Class<?> messageClass) {
        Method selected = null;
        for (Method candidate : candidates) {
            if (!isStatusMapper(candidate, messageClass)) continue;
            if (selected != null && !selected.equals(candidate)) return null;
            selected = candidate;
        }
        return selected;
    }

    private static boolean isConcreteInstanceMethod(Method method) {
        return method != null && !method.isSynthetic() && !method.isBridge()
                && !Modifier.isStatic(method.getModifiers())
                && !Modifier.isAbstract(method.getModifiers());
    }

    private static Field uniqueInstanceField(Class<?> owner, Class<?> type) {
        Field selected = null;
        for (Class<?> current = owner; current != null && current != Object.class;
             current = current.getSuperclass()) {
            for (Field field : current.getDeclaredFields()) {
                if (Modifier.isStatic(field.getModifiers()) || field.isSynthetic()
                        || field.getType() != type) continue;
                if (selected != null) return null;
                selected = field;
            }
        }
        return selected;
    }

    private static Object storedAcknowledgement(Class<?> resultClass) {
        if (!resultClass.isEnum()) return null;
        Object[] values = resultClass.getEnumConstants();
        if (values == null || values.length != 4) return null;
        Set<String> names = new HashSet<>();
        Object stored = null;
        for (Object value : values) {
            String name = ((Enum<?>) value).name();
            names.add(name);
            if ("STORED".equals(name)) stored = value;
        }
        if (names.size() != 4 || !names.contains("STORED") || !names.contains("STORED_ORPHAN")
                || !names.contains("FAILED_TO_STORE") || !names.contains("DIDNT_STORE")) return null;
        return stored;
    }
}
