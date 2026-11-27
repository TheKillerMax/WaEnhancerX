package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.core.privacy.PrivacyToggle;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import java.lang.reflect.Method;
import java.util.LinkedHashSet;
import java.util.Set;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.query.FindClass;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.ClassMatcher;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.ClassData;
import org.luckypray.dexkit.result.MethodData;

/** Keeps received view-once media only through a verified message and SQL state contract. */
public class AntiViewOnceHook extends BaseFeature {
    private static final String TAG = "[WAEX][AntiViewOnce]";
    private final Set<Method> installed = new LinkedHashSet<>();

    public AntiViewOnceHook(@NonNull Context context, @NonNull ClassLoader classLoader,
                           @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public synchronized void hook() throws Throwable {
        if (!installed.isEmpty()) return;
        installStateHooks();
        if (installed.isEmpty()) {
            throw new IllegalStateException("View-once contract unavailable");
        }
    }

    private void installStateHooks() {
        ViewOnceMessageContract messages;
        Set<Method> targets;
        try {
            DexSearchEngine.getInstance().initialize(context);
            DexKitBridge bridge = DexSearchEngine.getInstance().getBridge();
            if (bridge == null) return;
            messages = ViewOnceMessageContract.resolve(bridge, classLoader);
            if (messages == null) return;
            targets = sqlSetters(bridge, messages);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
            logFailure("State contract unavailable", failure);
            return;
        }
        for (Method target : targets) {
            try {
                // BaseFeature routes this registration through the tracked HookRegistrar.
                XposedBridge.hookMethod(target, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (!getPrivacy().isOn(PrivacyToggle.ANTI_VIEW_ONCE)) return;
                        if (param.args == null || param.args.length != 1
                                || !(param.args[0] instanceof Integer)
                                || (Integer) param.args[0] != 1) return;
                        if (messages.isIncoming(param.thisObject)) param.args[0] = 0;
                    }
                });
                installed.add(target);
            } catch (RuntimeException | LinkageError failure) {
                logFailure("Setter installation failed", failure);
                // FeatureRegistry discards this instance and removes already retained hooks.
                throw new IllegalStateException("View-once contract unavailable");
            }
        }
    }

    private Set<Method> sqlSetters(DexKitBridge bridge, ViewOnceMessageContract messages)
            throws ReflectiveOperationException {
        Set<Method> contracts = new LinkedHashSet<>();
        for (MethodData caller : bridge.findMethod(FindMethod.create().matcher(MethodMatcher.create()
                .addUsingString("INSERT_VIEW_ONCE_SQL", StringMatchType.Equals)))) {
            Set<Method> candidates = new LinkedHashSet<>();
            for (MethodData invoke : caller.getInvokes()) {
                if (!invoke.isMethod()) continue;
                Method invoked = invoke.getMethodInstance(classLoader);
                Method setter = ViewOnceMessageContract.interfaceSetter(invoked);
                if (setter != null) candidates.add(setter);
            }
            if (candidates.size() > 1) {
                throw new NoSuchMethodException("Ambiguous SQL view-once state interface");
            }
            contracts.addAll(candidates);
        }
        Set<Method> targets = new LinkedHashSet<>();
        // Multiple SQL callers may use the same interface; distinct interfaces are unverified.
        if (contracts.size() != 1) return targets;
        Method contract = contracts.iterator().next();
        for (ClassData data : bridge.findClass(FindClass.create().matcher(ClassMatcher.create()
                .addInterface(contract.getDeclaringClass().getName())))) {
            Class<?> type = data.getInstance(classLoader);
            if (!messages.isMessageType(type)) continue;
            Method target = type.getMethod(contract.getName(), int.class);
            if (messages.accepts(target)) targets.add(target);
        }
        return targets;
    }

    private static void logFailure(String action, Throwable failure) {
        XposedBridge.log(TAG + " " + action + ": " + failure.getClass().getSimpleName());
    }

    @NonNull
    @Override
    public String getName() {
        return "Anti-View Once";
    }
}
