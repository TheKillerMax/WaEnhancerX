package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.app.Activity;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.Toast;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.features.homescreen.MenuIconLoader;
import com.waenhancer.xposed.utils.ActivityTracker;
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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Blue on Reply Hook:
 * Defers sending blue read ticks until the user actually sends a reply message to the contact/group.
 */
public class BlueOnReplyHook extends BaseFeature {

    private static final String TAG = "[WAEX][BlueOnReply]";
    private static final String PREF_KEY = "blueonreply";
    // Bound retained constructor arguments and never route one chat's read receipts to another.
    private static final PendingReadReceiptStore<ReadJobRecipe> PENDING_JOBS =
            new PendingReadReceiptStore<>(128, 64);
    private static volatile Constructor<?> sendReadConstructor;
    private static volatile Method enqueueJobMethod;
    private static volatile Class<?> managerClass;
    private static volatile Object jobManager;
    private static final int MENU_SEND_BLUE_TICK = 0x7EAE0012;

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
        hookConversationMenu();
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

            Class<?> declaringManagerClass = anchor.getDeclaringClass();
            managerClass = declaringManagerClass;
            Class<?> baseJobClass = XposedHelpers.findClassIfExists(
                    "org.whispersystems.jobqueue.Job", classLoader);
            for (Method method : declaringManagerClass.getDeclaredMethods()) {
                if (method.getParameterCount() != 1) continue;
                Class<?> parameter = method.getParameterTypes()[0];
                boolean exactJobMethod = baseJobClass != null && parameter == baseJobClass;
                boolean compatibleJobMethod = baseJobClass == null
                        && parameter.isAssignableFrom(sendReadClass);
                if (exactJobMethod || compatibleJobMethod) {
                    method.setAccessible(true);
                    enqueueJobMethod = method;
                    break;
                }
            }
            if (enqueueJobMethod == null) return;

            // Try to find singleton instance if already created
            getOrFindJobManager();

            XposedBridge.hookAllConstructors(declaringManagerClass, new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    jobManager = param.thisObject;
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error initializing receipt dispatcher: " + t.getClass().getSimpleName());
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

                        // Use the outgoing job's actual recipient, not the Activity currently
                        // in the foreground: a queued send may belong to another conversation.
                        String remoteJid = extractOutgoingJobJid(param.thisObject);
                        if (remoteJid != null) sendPendingReadJobs(remoteJid);
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking Blue on Reply: " + t.getClass().getSimpleName());
        }
    }

    public boolean isBlueOnReplyEnabled() {
        return isHideBlueTicksEnabled() && isEnabled(PREF_KEY, false);
    }

    public static void captureSuppressedReadJob(String jid, Constructor<?> constructor,
                                                Object[] constructorArgs) {
        String key = canonicalJid(jid);
        if (key == null || constructor == null || constructorArgs == null) return;
        Object[] copy = Arrays.copyOf(constructorArgs, constructorArgs.length);
        for (int i = 0; i < copy.length; i++) {
            if (copy[i] instanceof String[]) {
                copy[i] = ((String[]) copy[i]).clone();
            }
        }
        constructor.setAccessible(true);
        PENDING_JOBS.add(key, new ReadJobRecipe(constructor, copy));
        XposedBridge.log(TAG + " Captured hidden read job (pending="
                + PENDING_JOBS.pendingCount(key) + ")");
    }

    private static Object getOrFindJobManager() {
        if (jobManager != null) return jobManager;
        if (managerClass != null) {
            try {
                for (Field field : managerClass.getDeclaredFields()) {
                    if (Modifier.isStatic(field.getModifiers()) && managerClass.isAssignableFrom(field.getType())) {
                        field.setAccessible(true);
                        Object instance = field.get(null);
                        if (instance != null) {
                            jobManager = instance;
                            return jobManager;
                        }
                    }
                }
            } catch (Throwable ignored) {}
        }
        return null;
    }

    private static int sendPendingReadJobs(String jid) {
        String key = canonicalJid(jid);
        if (key == null) {
            // Preserve upstream's exact outgoing-recipient guard and sanitized diagnostic.
            XposedBridge.log(TAG + " Cannot dispatch: outgoing recipient is unavailable");
            return 0;
        }

        Method enqueue = enqueueJobMethod;
        Object manager = getOrFindJobManager();
        if (enqueue == null || manager == null) {
            XposedBridge.log(TAG + " Cannot dispatch: WaJobManager or enqueueJobMethod is not ready");
            return 0;
        }

        // Exact canonical JID match only. @lid, @s.whatsapp.net and @g.us are
        // distinct identity namespaces; same local user part is NOT proof that
        // their queued read receipts belong to the same recipient.
        List<ReadJobRecipe> pending = PENDING_JOBS.drain(key);
        if (pending.isEmpty()) {
            XposedBridge.log(TAG + " No captured read jobs for reply");
            return 0;
        }

        // Do not authorize an entire JID: only IDs from explicitly enqueued jobs.
        int sent = 0;
        for (ReadJobRecipe recipe : pending) {
            try {
                HideReceiptsHook.allowExplicitReceiptIds(key, recipe.arguments);
                Object job = recipe.constructor.newInstance(recipe.arguments);
                XposedHelpers.setAdditionalInstanceField(job, "blue_on_reply", true);
                enqueue.invoke(manager, job);
                sent++;
                XposedBridge.log(TAG + " Enqueued blue-on-reply receipt");
            } catch (Throwable t) {
                // Constructor or dispatch failure must not leave a stale permission.
                HideReceiptsHook.revokeExplicitReceiptIds(key, recipe.arguments);
                XposedBridge.log(TAG + " Error enqueueing read receipt: "
                        + t.getClass().getSimpleName());
            }
        }
        return sent;
    }

    /**
     * The verified SendE2EMessageJob host declares a String field named "jid".
     * Never scan arbitrary job fields: they may contain participant or device IDs
     * that are valid JIDs but do not identify the outbound conversation.
     * Unknown hosts fail closed rather than releasing another chat's receipts.
     */
    private static String extractOutgoingJobJid(Object job) {
        if (job == null) return null;
        try {
            Object value = XposedHelpers.getObjectField(job, "jid");
            return value instanceof String
                    ? ReceiptJidPolicy.canonical((String) value) : null;
        } catch (Throwable ignored) {
            return null;
        }
    }

    private void hookConversationMenu() {
        try {
            Class<?> conversationClass = XposedHelpers.findClassIfExists(
                    "com.whatsapp.Conversation", classLoader);
            if (conversationClass == null) {
                XposedBridge.log(TAG + " Conversation class not found");
                return;
            }

            Set<Method> menuMethods = new LinkedHashSet<>();
            Class<?> current = conversationClass;
            while (current != null && current != Object.class) {
                String className = current.getName();
                if (className.startsWith("android.") || className.startsWith("androidx.")) break;
                for (Method method : current.getDeclaredMethods()) {
                    Class<?>[] parameters = method.getParameterTypes();
                    for (Class<?> parameter : parameters) {
                        if (parameter == Menu.class) {
                            menuMethods.add(method);
                            break;
                        }
                    }
                }
                current = current.getSuperclass();
            }
            if (menuMethods.isEmpty()) {
                XposedBridge.log(TAG + " No Conversation method accepting Menu found");
                return;
            }

            XC_MethodHook menuHook = new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    // Some menu methods live on a base activity shared by HomeActivity and
                    // Conversation. A hook on that declaration runs for every subclass, so never
                    // inject unless the current receiver is the real chat screen.
                    if (param.thisObject == null
                            || !conversationClass.isInstance(param.thisObject)) return;
                    Menu menu = null;
                    for (Object argument : param.args) {
                        if (argument instanceof Menu) {
                            menu = (Menu) argument;
                            break;
                        }
                    }
                    injectConversationMenuItem(menu, param.thisObject);
                }
            };
            for (Method menuMethod : menuMethods) {
                menuMethod.setAccessible(true);
                XposedBridge.hookMethod(menuMethod, menuHook);
                XposedBridge.log(TAG + " Hooked Conversation menu method: " + menuMethod);
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error adding conversation blue-tick menu: " + t.getClass().getSimpleName());
        }
    }

    private void injectConversationMenuItem(Menu menu, Object conversation) {
        if (menu == null) return;
        if (!isManualButtonEnabled()) {
            menu.removeItem(MENU_SEND_BLUE_TICK);
            return;
        }
        if (menu.findItem(MENU_SEND_BLUE_TICK) != null) return;

        MenuItem item = menu.add(Menu.NONE, MENU_SEND_BLUE_TICK, Menu.NONE, "Send blue tick");
        android.graphics.drawable.Drawable icon = MenuIconLoader.load(context, "ic_waex_mark_read");
        if (icon == null) {
            int iconId = context.getResources().getIdentifier(
                    "ic_notif_mark_read", "drawable", "com.whatsapp");
            if (iconId != 0) item.setIcon(iconId);
        } else {
            item.setIcon(icon);
        }
        item.setShowAsAction(manualButtonPlacement() == 1
                ? MenuItem.SHOW_AS_ACTION_ALWAYS : MenuItem.SHOW_AS_ACTION_NEVER);
        item.setOnMenuItemClickListener(clicked -> {
            String jid = resolveConversationJid(conversation);
            int sent = jid == null ? 0 : sendPendingReadJobs(jid);
            Context toastContext = conversation instanceof Context
                    ? (Context) conversation : context;
            Toast.makeText(toastContext,
                    jid == null ? "Cannot verify chat recipient"
                            : (sent > 0 ? "Blue tick sent" : "No hidden read receipt to send"),
                    Toast.LENGTH_SHORT).show();
            return true;
        });
    }

    private boolean isManualButtonEnabled() {
        if (!isHideBlueTicksEnabled()) return false;
        Object value = prefs.getAll().get("seentick");
        if (value instanceof Boolean) return (Boolean) value;
        if (value instanceof Number) return ((Number) value).intValue() != 0;
        if (value instanceof String) {
            String text = (String) value;
            return !text.isEmpty() && !"0".equals(text) && !"false".equalsIgnoreCase(text);
        }
        return false;
    }

    private boolean isHideBlueTicksEnabled() {
        return isEnabled("hide_read_receipts", false) || isEnabled("hideread", false);
    }

    /** 1 = toolbar icon, 2 = overflow menu. Boolean legacy values migrate as toolbar mode. */
    private int manualButtonPlacement() {
        Object value = prefs.getAll().get("seentick");
        if (value instanceof String) {
            try {
                return Integer.parseInt((String) value);
            } catch (NumberFormatException ignored) {
                return 0;
            }
        }
        return isManualButtonEnabled() ? 1 : 0;
    }

    /**
     * For a manual user action, require an explicit and unambiguous chat address.
     * Scanning the Activity's fields or arbitrary Intent extras risks selecting a
     * different contact's pending receipt job, so unknown hosts fail closed.
     */
    private String resolveConversationJid(Object conversation) {
        if (!(conversation instanceof Activity)) return null;
        try {
            Intent intent = ((Activity) conversation).getIntent();
            if (intent == null) return null;
            List<String> candidates = new ArrayList<>();
            if (intent.getData() != null) {
                String exactData = canonicalJid(intent.getData().toString());
                if (exactData != null) candidates.add(exactData);
            }
            Bundle extras = intent.getExtras();
            if (extras != null) {
                String[] keys = {"jid", "chat_jid", "remote_jid",
                        "extra_chat_jid", "conversation_jid"};
                for (String key : keys) {
                    if (!extras.containsKey(key)) continue;
                    String value = extractJidString(extras.get(key));
                    if (value == null) return null;
                    candidates.add(value);
                }
            }
            return ConversationRecipientPolicy.resolve(candidates);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static String extractJidString(Object obj) {
        if (obj == null) return null;
        if (obj instanceof String) {
            return canonicalJid((String) obj);
        }
        try {
            Object raw = XposedHelpers.callMethod(obj, "getRawString");
            if (raw != null) {
                String c = canonicalJid(raw.toString());
                if (c != null) return c;
            }
        } catch (Throwable ignored) {}
        return canonicalJid(obj.toString());
    }

    private static String canonicalJid(String value) {
        return ReceiptJidPolicy.canonical(value);
    }

    @NonNull
    @Override
    public String getName() {
        return "Blue on Reply";
    }
}
