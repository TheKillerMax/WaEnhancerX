package com.waenhancer.xposed.features.media;

import android.content.Context;
import android.view.Menu;
import android.view.MenuInflater;
import android.view.MenuItem;

import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.result.MethodData;
import org.luckypray.dexkit.result.UsingFieldData;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;

/**
 * Resolves the same page/message/media/file path used by the host media menu.
 * Discovery is confined to named viewer classes and their actual call/field edges.
 * No object graph, filename, numeric resource ID, or first-match fallback is used.
 */
final class ViewOnceMediaResolver {
    private static final String VIEWER = "com.whatsapp.mediaview.MediaViewFragment";
    private static final String MENU_OWNER = "com.whatsapp.mediaview.menu.MediaViewMenu";
    private static final String PAGER = "androidx.viewpager.widget.ViewPager";
    private ViewOnceMediaResolver() {}

    interface Metadata {
        Collection<Method> calls(Method method) throws ReflectiveOperationException;
        Collection<Field> reads(Method method) throws ReflectiveOperationException;
    }

    static Contract discover(DexKitBridge bridge, ClassLoader loader)
            throws ReflectiveOperationException {
        return discover(
                Class.forName(VIEWER, false, loader),
                Class.forName(MENU_OWNER, false, loader),
                Class.forName("androidx.fragment.app.Fragment", false, loader),
                Class.forName(PAGER, false, loader),
                Class.forName("com.whatsapp.infra.core.jid.Jid", false, loader),
                new Metadata() {
                    @Override public Collection<Method> calls(Method method)
                            throws ReflectiveOperationException {
                        MethodData data = bridge.getMethodData(method);
                        if (data == null) throw new IllegalArgumentException("Missing viewer method");
                        List<Method> result = new ArrayList<>();
                        for (MethodData called : data.getInvokes()) {
                            if (!called.isMethod()) continue;
                            // Read signature metadata before resolving classes. A media
                            // menu also calls optional sharing/payment/editor services;
                            // those classes are unrelated to this export contract.
                            if (method.getDeclaringClass().getName().equals(MENU_OWNER)) {
                                if (called.getParamCount() != 0
                                        || !called.getReturnTypeName().equals(File.class.getName())) continue;
                            } else {
                                String owner = called.getDeclaredClassName();
                                if (!owner.equals(VIEWER) && !owner.equals(MENU_OWNER) && !owner.equals(PAGER)) continue;
                            }
                            result.add(called.getMethodInstance(loader));
                        }
                        return result;
                    }

                    @Override public Collection<Field> reads(Method method)
                            throws ReflectiveOperationException {
                        MethodData data = bridge.getMethodData(method);
                        if (data == null) throw new IllegalArgumentException("Missing viewer method");
                        List<Field> result = new ArrayList<>();
                        LinkedHashSet<String> messageOwners = new LinkedHashSet<>();
                        if (method.getDeclaringClass().getName().equals(MENU_OWNER)) {
                            Class<?> type = method.getParameterTypes()[2];
                            while (type != null && type != Object.class) {
                                messageOwners.add(type.getName());
                                type = type.getSuperclass();
                            }
                        }
                        for (UsingFieldData use : data.getUsingFields()) {
                            if (use.getUsingType().isRead()) {
                                if (!messageOwners.isEmpty()
                                        && !messageOwners.contains(use.getField().getDeclaredClassName())) continue;
                                result.add(use.getField().getFieldInstance(loader));
                            }
                        }
                        return result;
                    }
                });
    }

    static Contract discover(Class<?> viewer, Class<?> menuOwner, Class<?> fragment,
                             Class<?> pager, Class<?> jid, Metadata metadata)
            throws ReflectiveOperationException {
        if (!fragment.isAssignableFrom(viewer)) throw incompatible();
        Method selectEvent = viewer.getDeclaredMethod("onOptionsItemSelected", MenuItem.class);
        if (!instanceMethod(selectEvent) || selectEvent.getReturnType() != boolean.class) throw incompatible();

        // This getter takes the current page index; the zero-argument getter returns
        // the initial message on the audited host and must not replace it.
        List<Method> currentCandidates = new ArrayList<>();
        Collection<Method> selectionCalls = metadata.calls(selectEvent);
        for (Method method : selectionCalls) {
            if (concrete(method) && Modifier.isStatic(method.getModifiers())
                    && method.getDeclaringClass() == viewer
                    && Arrays.equals(method.getParameterTypes(), new Class<?>[]{viewer, int.class})
                    && !method.getReturnType().isPrimitive()
                    && method.getReturnType() != Object.class) currentCandidates.add(method);
        }
        Method currentMessage = unique(currentCandidates);
        Class<?> mediaMessage = currentMessage.getReturnType();

        List<Method> clickCandidates = new ArrayList<>();
        for (Method method : selectionCalls) {
            if (instanceMethod(method) && method.getDeclaringClass() == menuOwner
                    && method.getReturnType() == void.class
                    && Arrays.equals(method.getParameterTypes(),
                        new Class<?>[]{MenuItem.class, fragment, mediaMessage, int.class})) {
                clickCandidates.add(method);
            }
        }
        Method menuClick = unique(clickCandidates);

        List<Method> createCandidates = new ArrayList<>();
        List<Method> initializeCandidates = new ArrayList<>();
        List<Method> prepareCandidates = new ArrayList<>();
        Method currentIndex = pager.getMethod("getCurrentItem");
        if (!instanceMethod(currentIndex) || currentIndex.getReturnType() != int.class) throw incompatible();
        for (Method method : viewer.getDeclaredMethods()) {
            if (!instanceMethod(method) || method.getReturnType() != void.class) continue;
            Class<?>[] types = method.getParameterTypes();
            if (Arrays.equals(types, new Class<?>[]{MenuInflater.class, Menu.class})) {
                List<Method> initializers = new ArrayList<>();
                for (Method call : metadata.calls(method)) {
                    Class<?>[] p = call.getParameterTypes();
                    if (instanceMethod(call) && call.getDeclaringClass() == menuOwner
                            && call.getReturnType() == void.class && p.length == 7
                            && p[0] == Context.class && p[1] == Menu.class && p[2] == fragment
                            && jid.isAssignableFrom(p[3]) && p[4].isAssignableFrom(mediaMessage)
                            && p[4] != Object.class && p[5] == int.class && p[6] == boolean.class) {
                        initializers.add(call);
                    }
                }
                if (!initializers.isEmpty()) {
                    createCandidates.add(method);
                    initializeCandidates.add(unique(initializers));
                }
            } else if (Arrays.equals(types, new Class<?>[]{Menu.class})) {
                Collection<Method> calls = metadata.calls(method);
                if (calls.contains(currentMessage) && calls.contains(currentIndex)) prepareCandidates.add(method);
            }
        }
        Method createMenu = unique(createCandidates);
        Method prepareMenu = unique(prepareCandidates);
        Method initializeMenu = unique(initializeCandidates);
        Class<?> messageBase = initializeMenu.getParameterTypes()[4];
        Class<?> chatType = initializeMenu.getParameterTypes()[3];

        List<Field> pagers = new ArrayList<>();
        for (Field field : metadata.reads(prepareMenu)) {
            if (!Modifier.isStatic(field.getModifiers())
                    && field.getDeclaringClass().isAssignableFrom(viewer)
                    && pager.isAssignableFrom(field.getType())) pagers.add(field);
        }
        Field pagerField = unique(pagers);

        List<Method> files = new ArrayList<>();
        for (Method method : metadata.calls(menuClick)) {
            if (instanceMethod(method) && method.getParameterCount() == 0
                    && method.getReturnType() == File.class) files.add(method);
        }
        Method fileGetter = unique(files);
        List<Field> mediaFields = new ArrayList<>();
        List<Field> keys = new ArrayList<>();
        for (Field field : metadata.reads(menuClick)) {
            if (Modifier.isStatic(field.getModifiers())) continue;
            if (field.getDeclaringClass() == mediaMessage && field.getType() == fileGetter.getDeclaringClass()) {
                mediaFields.add(field);
            }
            if (field.getDeclaringClass() == messageBase && Modifier.isFinal(field.getModifiers())
                    && !field.getType().isPrimitive() && field.getType() != String.class) keys.add(field);
        }
        Field media = unique(mediaFields);
        Field key = unique(keys);
        Class<?> keyType = key.getType();
        keyType.getDeclaredConstructor(chatType, String.class, boolean.class);
        List<Field> chatFields = new ArrayList<>();
        List<Field> ids = new ArrayList<>();
        List<Field> ownFields = new ArrayList<>();
        int keyFields = 0;
        for (Field field : keyType.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers())) continue;
            if (!Modifier.isFinal(field.getModifiers())) throw incompatible();
            keyFields++;
            if (field.getType() == chatType) chatFields.add(field);
            else if (field.getType() == String.class) ids.add(field);
            else if (field.getType() == boolean.class) ownFields.add(field);
        }
        if (keyFields != 3) throw incompatible();
        Method rawJid = jid.getMethod("getRawString");
        if (rawJid.getReturnType() != String.class || Modifier.isStatic(rawJid.getModifiers())) throw incompatible();
        return new Contract(viewer, createMenu, prepareMenu, currentMessage, currentIndex,
                pagerField, media, fileGetter, key, unique(chatFields), unique(ids), unique(ownFields), rawJid);
    }

    private static boolean concrete(Method method) {
        int flags = method.getModifiers();
        return Modifier.isPublic(flags) && !Modifier.isAbstract(flags) && !Modifier.isNative(flags)
                && !method.isBridge() && !method.isSynthetic();
    }

    private static boolean instanceMethod(Method method) {
        return concrete(method) && !Modifier.isStatic(method.getModifiers());
    }

    private static IllegalArgumentException incompatible() {
        return new IllegalArgumentException("Unsupported media viewer contract");
    }

    private static <T> T unique(Collection<T> candidates) {
        LinkedHashSet<T> distinct = new LinkedHashSet<>(candidates);
        if (distinct.size() != 1) throw incompatible();
        return distinct.iterator().next();
    }

    private static Object invoke(Method method, Object target, Object... arguments)
            throws ReflectiveOperationException {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException failure) {
            // Reflection must not turn a fatal host error into an ordinary optional-feature miss.
            Throwable cause = failure.getCause();
            if (cause instanceof VirtualMachineError) throw (VirtualMachineError) cause;
            if (cause instanceof ThreadDeath) throw (ThreadDeath) cause;
            throw failure;
        }
    }

    static final class Contract {
        final Class<?> viewerClass;
        final Method createMenu;
        final Method prepareMenu;
        private final Method currentMessage, currentIndex, fileGetter, rawJid;
        private final Field pager, media, key, chat, id, own;

        private Contract(Class<?> viewerClass, Method createMenu, Method prepareMenu,
                         Method currentMessage, Method currentIndex, Field pager, Field media,
                         Method fileGetter, Field key, Field chat, Field id, Field own, Method rawJid) {
            this.viewerClass = viewerClass;
            this.createMenu = createMenu;
            this.prepareMenu = prepareMenu;
            this.currentMessage = currentMessage;
            this.currentIndex = currentIndex;
            this.pager = pager;
            this.media = media;
            this.fileGetter = fileGetter;
            this.key = key;
            this.chat = chat;
            this.id = id;
            this.own = own;
            this.rawJid = rawJid;
            for (Field field : new Field[]{pager, media, key, chat, id, own}) field.setAccessible(true);
            for (Method method : new Method[]{currentMessage, currentIndex, fileGetter, rawJid}) method.setAccessible(true);
        }

        /** Called only for an explicit menu click on the UI caller, before queuing file IO. */
        File fileAtCurrentPage(Object viewer) throws ReflectiveOperationException {
            if (!viewerClass.isInstance(viewer)) return null;
            Object page = pager.get(viewer);
            if (page == null) return null;
            int index = (Integer) invoke(currentIndex, page);
            if (index < 0) return null;
            Object message = invoke(currentMessage, null, viewer, index);
            if (!currentMessage.getReturnType().isInstance(message)) return null;
            Identity before = identity(message);
            Object data = media.get(message);
            if (before == null || data == null) return null;
            Object result = invoke(fileGetter, data);
            if (!(result instanceof File)) return null;

            // A callback/getter may change the page or replace its message. Never export
            // the old file under a newly selected row, chat or from-me identity.
            if (pager.get(viewer) != page || (Integer) invoke(currentIndex, page) != index) return null;
            Object current = invoke(currentMessage, null, viewer, index);
            if (!currentMessage.getReturnType().isInstance(current)
                    || !before.equals(identity(current)) || media.get(current) != data
                    || !before.equals(identity(message))) return null;
            return (File) result;
        }

        private Identity identity(Object message) throws ReflectiveOperationException {
            return identityFromKey(key.get(message));
        }

        Class<?> messageBase() { return key.getDeclaringClass(); }
        Class<?> keyType() { return key.getType(); }

        boolean hasMediaKey(Object message, Object expectedKey) throws ReflectiveOperationException {
            if (!currentMessage.getReturnType().isInstance(message)) return false;
            Identity expected = identityFromKey(expectedKey);
            return expected != null && expected.equals(identity(message));
        }

        File fileForKey(Object message, Object expectedKey) throws ReflectiveOperationException {
            if (!hasMediaKey(message, expectedKey)) return null;
            Identity expected = identityFromKey(expectedKey);
            Object data = media.get(message);
            if (data == null) return null;
            Object result = invoke(fileGetter, data);
            if (!(result instanceof File) || media.get(message) != data
                    || !expected.equals(identity(message))) return null;
            return (File) result;
        }

        private Identity identityFromKey(Object value) throws ReflectiveOperationException {
            if (!key.getType().isInstance(value)) return null;
            Object jid = chat.get(value);
            String messageId = (String) id.get(value);
            if (jid == null || messageId == null || messageId.isEmpty()) return null;
            String address = (String) invoke(rawJid, jid);
            if (address == null || address.isEmpty()) return null;
            return new Identity(address, messageId, own.getBoolean(value));
        }
    }

    private static final class Identity {
        final String chat, id;
        final boolean own;
        Identity(String chat, String id, boolean own) { this.chat = chat; this.id = id; this.own = own; }
        @Override public boolean equals(Object other) {
            if (!(other instanceof Identity)) return false;
            Identity value = (Identity) other;
            return own == value.own && chat.equals(value.chat) && id.equals(value.id);
        }
        @Override public int hashCode() { return Objects.hash(chat, id, own); }
    }
}
