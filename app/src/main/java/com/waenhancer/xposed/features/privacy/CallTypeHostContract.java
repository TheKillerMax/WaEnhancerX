package com.waenhancer.xposed.features.privacy;

import android.app.Activity;
import android.content.Context;
import android.view.View;
import com.waenhancer.utils.ContactIdentityPolicy;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * The outgoing conversation operations shared by classic and popup call menus.
 * No numeric menu ID, obfuscated method name, arbitrary Activity extra, or cached
 * "last chat" participates in selecting a recipient.
 */
final class CallTypeHostContract {
    private static final Set<String> LIFECYCLE_STATES = new HashSet<>(Arrays.asList(
            "DESTROYED", "INITIALIZED", "CREATED", "STARTED", "RESUMED"));
    final List<Site> sites;

    private CallTypeHostContract(List<Site> sites) {
        this.sites = java.util.Collections.unmodifiableList(sites);
    }

    static CallTypeHostContract discover(Context context, ClassLoader loader) throws Throwable {
        CallTypeHostProfile profile = CallTypeHostProfile.find(context);
        if (profile == null) throw new NoSuchMethodException("Call selector: unsupported host APK");
        Class<?> api = Class.forName(profile.apiName, false, loader);
        Class<?>[] arguments = new Class<?>[profile.argumentCount];
        Arrays.fill(arguments, boolean.class);
        Class<?> activity = Class.forName("com.whatsapp.Conversation", false, loader);
        Class<?> adapter = Class.forName(profile.adapterName, false, loader);
        CallTypeHostContract contract = resolve(Arrays.asList(
                api.getDeclaredMethod(profile.firstOperation, arguments),
                api.getDeclaredMethod(profile.secondOperation, arguments)), activity,
                Class.forName("com.whatsapp.conversation.ConversationFragment", false, loader),
                Class.forName("com.whatsapp.infra.core.jid.Jid", false, loader));
        for (int index = 0; index < contract.sites.size(); index++) {
            if (contract.sites.get(index).operation.getDeclaringClass() != (index < 2 ? activity : adapter)) {
                throw new NoSuchMethodException("Call selector: inspected conversation owner changed");
            }
        }
        return contract;
    }

    /** Reflection part also used by fixtures built from the verified host contract. */
    static CallTypeHostContract resolve(List<Method> calls, Class<?> activityOwner,
                                        Class<?> fragmentOwner, Class<?> jid)
            throws ReflectiveOperationException {
        if (calls.size() != 2 || new HashSet<>(calls).size() != 2
                || !Activity.class.isAssignableFrom(activityOwner)) {
            throw new NoSuchMethodException("Call selector: unsupported conversation owners");
        }
        Class<?> api = calls.get(0).getDeclaringClass();
        Class<?>[] arguments = calls.get(0).getParameterTypes();
        if (arguments.length != 3 && arguments.length != 4) {
            throw new NoSuchMethodException("Call selector: unsupported outgoing argument count");
        }
        for (Class<?> argument : arguments) {
            if (argument != boolean.class) {
                throw new NoSuchMethodException("Call selector: non-boolean outgoing argument");
            }
        }
        for (Method call : calls) {
            if (call.getDeclaringClass() != api || !api.isInterface()
                    || Modifier.isStatic(call.getModifiers()) || call.getReturnType() != void.class
                    || !Arrays.equals(call.getParameterTypes(), arguments)) {
                throw new NoSuchMethodException("Call selector: unsupported outgoing method shape");
            }
        }
        Method apiPeer = api.getMethod("getChatJid");
        if (!jid.isAssignableFrom(apiPeer.getReturnType())
                || Modifier.isStatic(apiPeer.getModifiers())) {
            throw new NoSuchMethodException("Call selector: current conversation JID is unavailable");
        }
        Method raw = jid.getDeclaredMethod("getRawString");
        requireInstance(raw, String.class, false);
        raw.setAccessible(true);
        Field adapterField = null;
        for (Field field : fragmentOwner.getDeclaredFields()) {
            if (!Modifier.isStatic(field.getModifiers())
                    && View.class.isAssignableFrom(field.getType())
                    && api.isAssignableFrom(field.getType())) {
                if (adapterField != null) {
                    throw new NoSuchFieldException("Call selector: multiple fragment conversation adapters");
                }
                adapterField = field;
            }
        }
        if (adapterField == null) throw new NoSuchFieldException("Call selector: fragment adapter is unavailable");
        adapterField.setAccessible(true);
        List<Site> sites = new ArrayList<>();
        for (Class<?> owner : new Class<?>[] {activityOwner, adapterField.getType()}) {
            if (!api.isAssignableFrom(owner)) {
                throw new NoSuchMethodException("Call selector: conversation does not implement outgoing API");
            }
            Method peer = owner.getMethod("getChatJid");
            requireInstance(peer, apiPeer.getReturnType(), false);
            Method lifecycle = owner.getMethod("getLifecycle");
            requireInstance(lifecycle, lifecycle.getReturnType(), false);
            Method state = findLifecycleState(lifecycle.getReturnType());
            Method activity = null;
            Method host = null;
            Field field = null;
            if (!Activity.class.isAssignableFrom(owner)) {
                activity = owner.getMethod("getActivityNullable");
                requireInstance(activity, activity.getReturnType(), false);
                if (!Activity.class.isAssignableFrom(activity.getReturnType())) {
                    throw new NoSuchMethodException("Call selector: adapter Activity is unavailable");
                }
                host = owner.getMethod("getHost");
                requireInstance(host, host.getReturnType(), false);
                if (!host.getReturnType().isAssignableFrom(fragmentOwner)) {
                    throw new NoSuchMethodException("Call selector: adapter Fragment is unavailable");
                }
                field = adapterField;
            }
            for (Method declaration : calls) {
                Method operation = owner.getDeclaredMethod(declaration.getName(), arguments);
                requireInstance(operation, void.class, false);
                operation.setAccessible(true);
                sites.add(new Site(operation, peer, raw, lifecycle, state, activity, host, field));
            }
        }
        return new CallTypeHostContract(sites);
    }

    private static Method findLifecycleState(Class<?> lifecycle) throws NoSuchMethodException {
        Method result = null;
        for (Method method : lifecycle.getMethods()) {
            if (method.getParameterTypes().length != 0 || !method.getReturnType().isEnum()
                    || Modifier.isStatic(method.getModifiers()) || method.isBridge() || method.isSynthetic()) continue;
            Set<String> values = new HashSet<>();
            for (Object value : method.getReturnType().getEnumConstants()) values.add(((Enum<?>) value).name());
            if (!values.equals(LIFECYCLE_STATES)) continue;
            if (result != null) throw new NoSuchMethodException("Call selector: ambiguous lifecycle state");
            result = method;
        }
        if (result == null) throw new NoSuchMethodException("Call selector: lifecycle state is unavailable");
        result.setAccessible(true);
        return result;
    }

    private static void requireInstance(Method method, Class<?> returns, boolean abstractAllowed)
            throws NoSuchMethodException {
        int flags = method.getModifiers();
        if (method.getReturnType() != returns || Modifier.isStatic(flags) || Modifier.isNative(flags)
                || (!abstractAllowed && Modifier.isAbstract(flags)) || method.isBridge() || method.isSynthetic()) {
            throw new NoSuchMethodException("Call selector: unsupported method shape");
        }
        method.setAccessible(true);
    }

    static final class Site {
        final Method operation;
        private final Method peer;
        private final Method raw;
        private final Method lifecycle;
        private final Method state;
        private final Method activity;
        private final Method host;
        private final Field adapter;

        Site(Method operation, Method peer, Method raw, Method lifecycle, Method state,
             Method activity, Method host, Field adapter) {
            this.operation = operation;
            this.peer = peer;
            this.raw = raw;
            this.lifecycle = lifecycle;
            this.state = state;
            this.activity = activity;
            this.host = host;
            this.adapter = adapter;
        }

        Snapshot read(Object owner) throws ReflectiveOperationException {
            if (owner == null || owner.getClass() != operation.getDeclaringClass()) return null;
            Object currentState = state.invoke(lifecycle.invoke(owner));
            if (!(currentState instanceof Enum<?>) || !((Enum<?>) currentState).name().equals("RESUMED")) return null;
            Activity currentActivity;
            if (activity == null) {
                currentActivity = (Activity) owner;
            } else {
                Object fragment = host.invoke(owner);
                if (!adapter.getDeclaringClass().isInstance(fragment) || adapter.get(fragment) != owner) return null;
                View view = (View) owner;
                if (!view.isAttachedToWindow() || !view.isShown()) return null;
                currentActivity = (Activity) activity.invoke(owner);
            }
            if (currentActivity == null || currentActivity.isFinishing() || currentActivity.isDestroyed()
                    || !currentActivity.getWindow().getDecorView().isAttachedToWindow()) return null;
            Object jid = peer.invoke(owner);
            if (!raw.getDeclaringClass().isInstance(jid)) return null;
            String canonical = ContactIdentityPolicy.canonicalJid((String) raw.invoke(jid));
            if (canonical == null || (ContactIdentityPolicy.phoneUser(canonical) == null
                    && !ContactIdentityPolicy.isLid(canonical))) return null;
            return new Snapshot(currentActivity, canonical);
        }
    }

    static final class Snapshot {
        final Activity activity;
        final String peer;

        Snapshot(Activity activity, String peer) {
            this.activity = activity;
            this.peer = peer;
        }
    }
}

