package com.waenhancer.xposed.features.media;

import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
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
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;

/** The tagged audio fragment carries the message already resolved by the host. */
final class ViewOnceAudioResolver {
    private static final String AUDIO_TAG = "view_once_audio";
    final Class<?> activityClass;
    final Method createMenu, prepareMenu;
    private final Class<?> audioClass;
    private final Method manager, fragmentByTag;
    private final Field activityKey, audioMessage;
    private final ViewOnceMediaResolver.Contract media;

    static ViewOnceAudioResolver discover(DexKitBridge bridge, ClassLoader loader,
                                         ViewOnceMediaResolver.Contract media)
            throws ReflectiveOperationException {
        Class<?> activity = Class.forName("com.whatsapp.viewonce.ui.messaging.ViewOnceViewerActivity", false, loader);
        Class<?> audio = Class.forName("com.whatsapp.viewonce.ui.messaging.ViewOnceAudioFragment", false, loader);
        Class<?> fragment = Class.forName("androidx.fragment.app.Fragment", false, loader);
        if (!android.app.Activity.class.isAssignableFrom(activity) || !fragment.isAssignableFrom(audio)) throw unsupported();
        Method created = activity.getDeclaredMethod("onCreate", Bundle.class);
        Method createMenu = activity.getDeclaredMethod("onCreateOptionsMenu", Menu.class);
        Method prepareMenu = activity.getDeclaredMethod("onPrepareOptionsMenu", Menu.class);
        Method selected = activity.getDeclaredMethod("onOptionsItemSelected", MenuItem.class);
        for (Method method : new Method[]{created, createMenu, prepareMenu, selected}) {
            if (!instance(method)) throw unsupported();
            if (method.getReturnType() != (method.equals(created) ? void.class : boolean.class)) throw unsupported();
        }
        Method manager = activity.getMethod("getSupportFragmentManager");
        if (!instance(manager) || manager.getReturnType().isPrimitive() || manager.getReturnType() == Object.class) throw unsupported();
        MethodData createData = bridge.getMethodData(created);
        if (createData == null || !createData.getUsingStrings().contains(AUDIO_TAG)) throw unsupported();
        List<Method> managers = new ArrayList<>(), lookups = new ArrayList<>();
        for (MethodData call : createData.getInvokes()) {
            if (!call.isMethod()) continue;
            if (call.getName().equals(manager.getName()) && call.getParamCount() == 0
                    && call.getDeclaredClassName().equals(manager.getDeclaringClass().getName())
                    && call.getReturnTypeName().equals(manager.getReturnType().getName())) {
                managers.add(call.getMethodInstance(loader));
            }
            if (call.getDeclaredClassName().equals(manager.getReturnType().getName())
                    && call.getParamTypeNames().equals(Collections.singletonList(String.class.getName()))
                    && call.getReturnTypeName().equals(fragment.getName())) {
                Method lookup = call.getMethodInstance(loader);
                if (instance(lookup)) lookups.add(lookup);
            }
        }
        if (!unique(managers).equals(manager)) throw unsupported();
        Method byTag = unique(lookups);
        LinkedHashSet<Field> commonKeys = null;
        for (Method event : new Method[]{created, prepareMenu, selected}) {
            MethodData data = bridge.getMethodData(event);
            if (data == null) throw unsupported();
            LinkedHashSet<Field> keys = new LinkedHashSet<>();
            for (UsingFieldData use : data.getUsingFields()) {
                if (!use.getUsingType().isRead()
                        || !use.getField().getDeclaredClassName().equals(activity.getName())
                        || !use.getField().getTypeName().equals(media.keyType().getName())) continue;
                Field field = use.getField().getFieldInstance(loader);
                if (!Modifier.isStatic(field.getModifiers())) keys.add(field);
            }
            if (commonKeys == null) commonKeys = keys;
            else commonKeys.retainAll(keys);
        }
        Field key = unique(commonKeys);
        LinkedHashSet<String> audioOwners = new LinkedHashSet<>();
        for (Class<?> owner = audio; owner != null; owner = owner.getSuperclass()) audioOwners.add(owner.getName());
        List<Field> messages = new ArrayList<>();
        List<Method> bindings = new ArrayList<>();
        for (Method method : audio.getDeclaredMethods()) {
            if (!instance(method) || method.getReturnType() != void.class
                    || !Arrays.equals(method.getParameterTypes(), new Class<?>[]{Bundle.class, View.class})) continue;
            MethodData data = bridge.getMethodData(method);
            if (data == null || !data.getUsingStrings().contains("fMessage")) continue;
            bindings.add(method);
            for (UsingFieldData use : data.getUsingFields()) {
                if (!use.getUsingType().isRead() || !use.getField().getTypeName().equals(media.messageBase().getName())
                        || !audioOwners.contains(use.getField().getDeclaredClassName())) continue;
                Field field = use.getField().getFieldInstance(loader);
                if (!Modifier.isStatic(field.getModifiers()) && field.getDeclaringClass().isAssignableFrom(audio)) messages.add(field);
            }
        }
        unique(bindings);
        return new ViewOnceAudioResolver(activity, audio, createMenu, prepareMenu, manager, byTag,
                key, unique(messages), media);
    }

    private ViewOnceAudioResolver(Class<?> activity, Class<?> audio, Method createMenu, Method prepareMenu,
                                  Method manager, Method byTag, Field key, Field message,
                                  ViewOnceMediaResolver.Contract media) {
        this.activityClass = activity; this.audioClass = audio; this.createMenu = createMenu;
        this.prepareMenu = prepareMenu; this.manager = manager; this.fragmentByTag = byTag;
        this.activityKey = key; this.audioMessage = message; this.media = media;
        key.setAccessible(true); message.setAccessible(true); manager.setAccessible(true); byTag.setAccessible(true);
    }

    boolean hasAudio(Object activity) throws ReflectiveOperationException {
        Object audio = audio(activity);
        return audio != null && media.hasMediaKey(audioMessage.get(audio), activityKey.get(activity));
    }

    File fileAtActivity(Object activity) throws ReflectiveOperationException {
        Object audio = audio(activity);
        if (audio == null) return null;
        Object message = audioMessage.get(audio);
        Object key = activityKey.get(activity);
        File file = media.fileForKey(message, key);
        if (file == null || audio(activity) != audio || audioMessage.get(audio) != message
                || !media.hasMediaKey(message, activityKey.get(activity))) return null;
        return file;
    }

    private Object audio(Object activity) throws ReflectiveOperationException {
        if (!activityClass.isInstance(activity)) return null;
        Object fragmentManager = invoke(manager, activity);
        if (fragmentManager == null) return null;
        Object fragment = invoke(fragmentByTag, fragmentManager, AUDIO_TAG);
        return audioClass.isInstance(fragment) ? fragment : null;
    }

    private static Object invoke(Method method, Object receiver, Object... arguments) throws ReflectiveOperationException {
        try { return method.invoke(receiver, arguments); }
        catch (InvocationTargetException failure) {
            Throwable cause = failure.getCause();
            if (cause instanceof VirtualMachineError) throw (VirtualMachineError) cause;
            if (cause instanceof ThreadDeath) throw (ThreadDeath) cause;
            throw failure;
        }
    }
    private static boolean instance(Method method) {
        int modifiers = method.getModifiers();
        return Modifier.isPublic(modifiers) && !Modifier.isStatic(modifiers) && !Modifier.isAbstract(modifiers)
                && !Modifier.isNative(modifiers) && !method.isSynthetic() && !method.isBridge();
    }
    private static IllegalArgumentException unsupported() { return new IllegalArgumentException("Unsupported audio viewer contract"); }
    private static <T> T unique(Collection<T> values) {
        LinkedHashSet<T> distinct = new LinkedHashSet<>(values);
        if (distinct.size() != 1) throw unsupported();
        return distinct.iterator().next();
    }
}
