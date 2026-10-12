package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import org.luckypray.dexkit.query.FindClass;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.ClassMatcher;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.ClassData;
import org.luckypray.dexkit.result.MethodData;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Blue on Reply Hook:
 * Defers sending blue read ticks until the user actually sends a reply message to the contact/group.
 */
public class BlueOnReplyHook extends BaseFeature {

    private static final String TAG = "[WAEX][BlueOnReply]";
    private static final String PREF_KEY = "blueonreply";
    private static final Pattern JID_PATTERN = Pattern.compile(
            "([0-9-]+)@(s\\.whatsapp\\.net|g\\.us|lid|broadcast)");
    private static final Map<String, CopyOnWriteArrayList<ReadJobRecipe>> PENDING_JOBS =
            new ConcurrentHashMap<>();
    private static volatile Constructor<?> sendReadConstructor;
    private static volatile Method enqueueJobMethod;
    private static volatile Object jobManager;

    private static final class ReadJobRecipe {
        final Constructor<?> constructor;
        final Object[] arguments;

        ReadJobRecipe(Constructor<?> constructor, Object[] arguments) {
            this.constructor = constructor;
            this.arguments = arguments;
        }
    }

    public BlueOnReplyHook(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public void hook() throws Throwable {
        initializeReadReceiptDispatcher();
        hookMessageSend();
    }

    private void initializeReadReceiptDispatcher() {
        try {
            Class<?> sendReadClass = DexSearchEngine.getInstance().findClassWithCache(
                    context, classLoader, "wpp_send_read_receipt_job_class",
                    (bridge, loader) -> {
                        ClassData data = bridge.findClass(FindClass.create().matcher(
                                ClassMatcher.create().className(
                                        "SendReadReceiptJob", StringMatchType.EndsWith)))
                                .firstOrNull();
                        return data != null ? data.getInstance(loader) : null;
                    });
            if (sendReadClass == null) return;

            Constructor<?>[] constructors = sendReadClass.getDeclaredConstructors();
            if (constructors.length == 0) return;
            sendReadConstructor = constructors[0];
            sendReadConstructor.setAccessible(true);

            Method anchor = DexSearchEngine.getInstance().findMethodWithCache(
                    context, classLoader, "wpp_wa_job_manager_start_anchor",
                    (bridge, loader) -> {
                        MethodData data = bridge.findMethod(FindMethod.create().matcher(
                                MethodMatcher.create().addUsingString(
                                        "WaJobManager/start", StringMatchType.Contains)))
                                .firstOrNull();
                        return data != null ? data.getMethodInstance(loader) : null;
                    });
            if (anchor == null) return;

            Class<?> managerClass = anchor.getDeclaringClass();
            for (Method method : managerClass.getDeclaredMethods()) {
                if (method.getParameterCount() == 1
                        && method.getParameterTypes()[0].isAssignableFrom(sendReadClass)) {
                    method.setAccessible(true);
                    enqueueJobMethod = method;
                    break;
                }
            }
            if (enqueueJobMethod == null) return;

            XposedBridge.hookAllConstructors(managerClass, new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    jobManager = param.thisObject;
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error initializing receipt dispatcher: " + t.getMessage());
        }
    }

    private void hookMessageSend() {
        try {
            Method sendMessageMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_blue_on_reply_send_e2e_job",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .paramCount(0)
                                        .addUsingString("SendE2EMessageJob/onRun", StringMatchType.Contains)
                                )
                        ).firstOrNull();
                        return md != null ? md.getMethodInstance(loader) : null;
                    }
            );

            if (sendMessageMethod != null) {
                XposedBridge.hookMethod(sendMessageMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (!isBlueOnReplyEnabled()) return;

                        String remoteJid = extractRemoteJid(param.thisObject);
                        if (remoteJid != null) {
                            sendPendingReadJobs(remoteJid);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking Blue on Reply: " + t.getMessage());
        }
    }

    public boolean isBlueOnReplyEnabled() {
        return isEnabled(PREF_KEY, false);
    }

    public static void captureSuppressedReadJob(String jid, Constructor<?> constructor,
                                                Object[] constructorArgs) {
        String key = canonicalJid(jid);
        if (key == null || constructor == null || constructorArgs == null) return;
        CopyOnWriteArrayList<ReadJobRecipe> pending =
                PENDING_JOBS.computeIfAbsent(key, ignored -> new CopyOnWriteArrayList<>());
        if (pending.size() >= 64) pending.remove(0);

        Object[] copy = Arrays.copyOf(constructorArgs, constructorArgs.length);
        for (int i = 0; i < copy.length; i++) {
            if (copy[i] instanceof String[]) {
                copy[i] = ((String[]) copy[i]).clone();
            }
        }
        constructor.setAccessible(true);
        pending.add(new ReadJobRecipe(constructor, copy));
    }

    private static void sendPendingReadJobs(String jid) {
        String key = canonicalJid(jid);
        Method enqueue = enqueueJobMethod;
        Object manager = jobManager;
        if (key == null || enqueue == null || manager == null) return;

        List<ReadJobRecipe> pending = PENDING_JOBS.remove(key);
        if (pending == null || pending.isEmpty()) return;
        HideReceiptsHook.allowBlueReplyReceipt(key);

        for (ReadJobRecipe recipe : pending) {
            try {
                Object job = recipe.constructor.newInstance(recipe.arguments);
                XposedHelpers.setAdditionalInstanceField(job, "blue_on_reply", true);
                enqueue.invoke(manager, job);
            } catch (Throwable t) {
                XposedBridge.log(TAG + " Error enqueueing read receipt: " + t.getMessage());
            }
        }
    }

    private String extractRemoteJid(Object source) {
        if (source == null) return null;
        try {
            Class<?> current = source.getClass();
            while (current != null && current != Object.class) {
                for (Field field : current.getDeclaredFields()) {
                    if (Modifier.isStatic(field.getModifiers())) continue;
                    field.setAccessible(true);
                    Object value = field.get(source);
                    if (value == null) continue;
                    String raw = value.toString();
                    if (raw.contains("@s.whatsapp.net") || raw.contains("@g.us")
                            || raw.contains("@lid") || raw.contains("@broadcast")) {
                        return raw;
                    }
                }
                current = current.getSuperclass();
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static String canonicalJid(String value) {
        if (value == null) return null;
        Matcher matcher = JID_PATTERN.matcher(value);
        return matcher.find() ? matcher.group(1) + "@" + matcher.group(2) : null;
    }

    @NonNull
    @Override
    public String getName() {
        return "Blue on Reply";
    }
}
