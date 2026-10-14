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
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
    private static volatile Class<?> managerClass;
    private static volatile Object jobManager;
    private static volatile String lastHiddenConversationJid;
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

                        String remoteJid = extractRemoteJid(param.thisObject);
                        if (remoteJid != null) {
                            String receiptJid = remoteJid;
                            Activity activity = ActivityTracker.getCurrentActivity();
                            if (activity != null
                                    && activity.getClass().getSimpleName().contains("Conversation")) {
                                String currentConversation = resolveConversationJid(activity);
                                if (currentConversation != null) receiptJid = currentConversation;
                            }
                            sendPendingReadJobs(receiptJid);
                        }
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
        lastHiddenConversationJid = key;
        XposedBridge.log(TAG + " Captured hidden read job (pending=" + pending.size() + ")");
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
        Method enqueue = enqueueJobMethod;
        Object manager = getOrFindJobManager();

        if (enqueue == null || manager == null) {
            XposedBridge.log(TAG + " Cannot dispatch: WaJobManager or enqueueJobMethod is not ready");
            return 0;
        }

        List<ReadJobRecipe> pending = null;
        String matchedKey = null;

        if (key != null) {
            pending = PENDING_JOBS.remove(key);
            if (pending != null && !pending.isEmpty()) {
                matchedKey = key;
            } else {
                // Match by user part / phone number prefix (e.g. 12345 in 12345@s.whatsapp.net or 12345@lid)
                String userPart = getUserPart(key);
                if (userPart != null && !userPart.isEmpty()) {
                    for (String candidateKey : PENDING_JOBS.keySet()) {
                        if (userPart.equals(getUserPart(candidateKey))) {
                            pending = PENDING_JOBS.remove(candidateKey);
                            if (pending != null && !pending.isEmpty()) {
                                matchedKey = candidateKey;
                                break;
                            }
                        }
                    }
                }
            }
        }

        // Fallback to last hidden conversation JID if still empty
        if ((pending == null || pending.isEmpty()) && lastHiddenConversationJid != null) {
            pending = PENDING_JOBS.remove(lastHiddenConversationJid);
            if (pending != null && !pending.isEmpty()) {
                matchedKey = lastHiddenConversationJid;
            }
        }

        // If still empty and there is exactly one pending conversation, drain it
        if ((pending == null || pending.isEmpty()) && PENDING_JOBS.size() == 1) {
            for (String singleKey : PENDING_JOBS.keySet()) {
                pending = PENDING_JOBS.remove(singleKey);
                if (pending != null && !pending.isEmpty()) {
                    matchedKey = singleKey;
                    break;
                }
            }
        }

        if (pending == null || pending.isEmpty()) {
            XposedBridge.log(TAG + " No captured read jobs for reply");
            return 0;
        }

        if (matchedKey != null) {
            HideReceiptsHook.allowBlueReplyReceipt(matchedKey);
        }
        if (key != null && !key.equals(matchedKey)) {
            HideReceiptsHook.allowBlueReplyReceipt(key);
        }

        int sent = 0;
        for (ReadJobRecipe recipe : pending) {
            try {
                HideReceiptsHook.allowExplicitReceiptIds(recipe.arguments);
                Object job = recipe.constructor.newInstance(recipe.arguments);
                XposedHelpers.setAdditionalInstanceField(job, "blue_on_reply", true);
                enqueue.invoke(manager, job);
                sent++;
                XposedBridge.log(TAG + " Enqueued blue-on-reply receipt");
            } catch (Throwable t) {
                XposedBridge.log(TAG + " Error enqueueing read receipt: " + t.getClass().getSimpleName());
            }
        }
        return sent;
    }

    private static String getUserPart(String jid) {
        if (jid == null) return null;
        int atIdx = jid.indexOf('@');
        return atIdx != -1 ? jid.substring(0, atIdx) : jid;
    }

    private String extractRemoteJid(Object source) {
        if (source == null) return null;
        // SendE2EMessageJob deliberately keeps this serialized field name stable. This is the
        // This exact field path avoids selecting participant/device JIDs from other fields.
        try {
            Object jid = XposedHelpers.getObjectField(source, "jid");
            if (jid != null) {
                String raw = jid.toString();
                if (canonicalJid(raw) != null) return raw;
            }
        } catch (Throwable ignored) {
        }
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
                    sent > 0 ? "Blue tick sent" : "No hidden read receipt to send",
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

    private String resolveConversationJid(Object conversation) {
        String reflected = extractRemoteJid(conversation);
        if (reflected != null) return reflected;
        if (conversation instanceof Activity) {
            try {
                Intent intent = ((Activity) conversation).getIntent();
                if (intent != null) {
                    // Check intent URI or data
                    if (intent.getData() != null) {
                        String rawData = intent.getData().toString();
                        String parsedData = canonicalJid(rawData);
                        if (parsedData != null) return parsedData;
                    }
                    Bundle extras = intent.getExtras();
                    if (extras != null) {
                        // Common WhatsApp conversation intent keys
                        String[] commonKeys = new String[]{"jid", "chat_jid", "remote_jid", "extra_chat_jid", "conversation_jid"};
                        for (String key : commonKeys) {
                            Object value = extras.get(key);
                            if (value != null) {
                                String parsed = extractJidString(value);
                                if (parsed != null) return parsed;
                            }
                        }
                        for (String key : extras.keySet()) {
                            Object value = extras.get(key);
                            if (value != null) {
                                String parsed = extractJidString(value);
                                if (parsed != null) return parsed;
                            }
                        }
                    }
                }
            } catch (Throwable ignored) {
            }
        }
        return lastHiddenConversationJid;
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
