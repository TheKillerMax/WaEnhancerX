package com.waenhancer.xposed.features.automation;


import com.waenhancer.app.R;
import com.waenhancer.utils.UiText;

import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Handler;
import android.os.Looper;
import android.os.BaseBundle;
import android.os.Bundle;
import android.os.Message;
import android.widget.Toast;
import androidx.annotation.NonNull;
import com.waenhancer.utils.ContactNameResolver;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.MethodData;
import org.luckypray.dexkit.result.MethodDataList;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collection;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * Presence & Activity Toasts Hook:
 * Displays real-time toast alerts when:
 * 1. Contacts view your status (`toast_viewed_status`).
 * 2. Contacts read your messages (`toast_viewed_message`).
 * 3. Contacts come online (`showonline` / `typing_online_toasts`).
 */
public class PresenceToastsHook extends BaseFeature {

    private static final String TAG = "[WAEX][PresenceToasts]";
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    // Bound asynchronous name lookups rather than allowing unbounded queued tasks.
    private static final ExecutorService TOAST_EXECUTOR = new ThreadPoolExecutor(
            0, 1, 30L, TimeUnit.SECONDS, new ArrayBlockingQueue<>(96),
            task -> {
                Thread thread = new Thread(task, "WAEX-toast-lookup");
                thread.setDaemon(true);
                return thread;
            },
            new ThreadPoolExecutor.DiscardOldestPolicy());
    private final ExecutorService asyncExecutor = TOAST_EXECUTOR;

    public PresenceToastsHook(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public void hook() throws Throwable {
        hookIncomingPresence();
        hookStatusViewedReceipt();
        hookOnInsertReceipt();
    }

    private void hookIncomingPresence() {
        try {
            Method presenceMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context, classLoader, "wpp_presence_message_handler_v4",
                    (bridge, loader) -> {
                        // The old available literal belongs to a multiplexed Runnable.
                        // Match the Handler envelope instead, including both event branches.
                        MethodDataList matches = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .name("handleMessage")
                                        .paramTypes("android.os.Message")
                                        .returnType("void")
                                        .addUsingString("MessageHandler/handleConnectionThreadReady connectionready",
                                                StringMatchType.Equals)
                                        .addUsingString("lastSeen", StringMatchType.Equals)
                                        .addUsingString("presence", StringMatchType.Equals)
                                        .addInvoke(MethodMatcher.create().returnType("void").paramCount(3)
                                                .addUsingString("MessageHandler/handleDisconnected error=",
                                                        StringMatchType.Equals))));
                        if (matches.size() != 1) return null;
                        Method candidate = matches.get(0).getMethodInstance(loader);
                        return isPresenceHandler(candidate) ? candidate : null;
                    });
            if (!isPresenceHandler(presenceMethod)) {
                XposedBridge.log(TAG + " Presence handler contract unavailable; online notifications not installed");
                return;
            }
            XposedBridge.hookMethod(presenceMethod, new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    // Observe only successfully handled host events. Never cancel/mutate them.
                    if (param.hasThrowable() || param.args == null || param.args.length != 1
                            || !(param.args[0] instanceof Message)) return;
                    if (PresenceEventPolicy.isTransportInvalidation(((Message) param.args[0]).what)) {
                        PresenceStateStore.invalidateAll();
                        return;
                    }
                    PresenceEventPolicy.Event event = decodePresenceEvent(param.args);
                    if (event == null) return;
                    if (!event.known) {
                        PresenceStateStore.invalidate(event.jid);
                        return;
                    }
                    final long transitionId = PresenceStateStore.updateAndGetTransition(event.jid, event.online);
                    if (transitionId != 0L && event.online && isOnlineToastEnabled()) {
                        asyncExecutor.execute(() -> {
                            if (!PresenceStateStore.isCurrentOnline(event.jid, transitionId)) return;
                            try {
                                String name = ContactNameResolver.INSTANCE.resolveName(context, event.jid, null, null);
                                showToastSafely(name + UiText.get(R.string.waex_ui_is_online_e0992fa5, " is online"), () -> isOnlineToastEnabled()
                                        && PresenceStateStore.isCurrentOnline(event.jid, transitionId));
                            } catch (RuntimeException | LinkageError ignored) { /* Optional name lookup. */ }
                        });
                    }
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking presence toasts: " + t.getClass().getSimpleName());
        }
    }

    private static boolean isPresenceHandler(Method method) {
        if (method == null || !Handler.class.isAssignableFrom(method.getDeclaringClass())) return false;
        int flags = method.getModifiers();
        Class<?>[] parameters = method.getParameterTypes();
        return java.lang.reflect.Modifier.isPublic(flags)
                && !java.lang.reflect.Modifier.isStatic(flags)
                && !java.lang.reflect.Modifier.isAbstract(flags)
                && !java.lang.reflect.Modifier.isNative(flags)
                && !method.isBridge() && !method.isSynthetic()
                && "handleMessage".equals(method.getName()) && method.getReturnType() == void.class
                && parameters.length == 1 && parameters[0] == Message.class;
    }

    private static PresenceEventPolicy.Event decodePresenceEvent(Object[] args) {
        if (args == null || args.length != 1 || !(args[0] instanceof Message)) return null;
        Message message = (Message) args[0];
        if (message.what != PresenceEventPolicy.EVENT_FAMILY
                || !PresenceEventPolicy.isPresenceCode(message.arg1)
                || !(message.obj instanceof BaseBundle)) return null;
        try {
            BaseBundle payload = (BaseBundle) message.obj;
            return PresenceEventPolicy.decode(message.what, message.arg1,
                    payload.get("jid"), payload.get("presence"));
        } catch (RuntimeException unreadablePayload) {
            return null;
        }
    }

    /**
     * Hooks StatusReceiptStore/insertOrUpdateSeenReceiptForStatus for real-time status viewed alerts.
     */
    private void hookStatusViewedReceipt() {
        try {
            Method statusReceiptMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_status_seen_receipt_store",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("StatusReceiptStore/insertOrUpdateSeenReceiptForStatus", StringMatchType.Contains)
                                )
                        ).firstOrNull();
                        return md != null ? md.getMethodInstance(loader) : null;
                    }
            );

            if (statusReceiptMethod != null) {
                XposedBridge.hookMethod(statusReceiptMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (!isStatusViewedToastEnabled()) return;

                        if (param.args != null && param.args.length > 0) {
                            Object jidObj = param.args[0];
                            String rawJid = jidObj != null ? jidObj.toString() : null;
                            if (rawJid != null && !rawJid.isEmpty()) {
                                asyncExecutor.execute(() -> {
                                    String contactName = ContactNameResolver.INSTANCE.resolveName(context, rawJid, null, null);
                                    showToastSafely(contactName + UiText.get(R.string.waex_ui_viewed_your_status_44b3e59c, " viewed your status"));
                                });
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking status viewed receipt: " + t.getMessage());
        }
    }

    /**
     * Hooks OnInsertReceipt for broader receipt status updates (Viewed status / Viewed messages).
     */
    private void hookOnInsertReceipt() {
        try {
            Method onInsertReceiptMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_on_insert_receipt_user",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("INSERT_RECEIPT_USER", StringMatchType.Contains)
                                        .paramCount(1)
                                )
                        ).firstOrNull();
                        return md != null ? md.getMethodInstance(loader) : null;
                    }
            );

            if (onInsertReceiptMethod != null) {
                XposedBridge.hookMethod(onInsertReceiptMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        boolean statusToast = isStatusViewedToastEnabled();
                        boolean msgToast = isMessageViewedToastEnabled();
                        if (!statusToast && !msgToast) return;

                        Object arg = param.args[0];
                        if (arg == null) return;

                        if (arg instanceof Collection) {
                            for (Object item : (Collection<?>) arg) {
                                processReceiptItem(item, statusToast, msgToast);
                            }
                        } else {
                            processReceiptItem(arg, statusToast, msgToast);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking onInsertReceipt: " + t.getMessage());
        }
    }

    private static final ToastThrottle TOAST_THROTTLE = new ToastThrottle(1500L, 2048);
    private static final java.util.concurrent.atomic.AtomicInteger PRESENCE_DIAGNOSTICS = new java.util.concurrent.atomic.AtomicInteger();

    private void processReceiptItem(Object receiptObj, boolean statusToast, boolean msgToast) {
        if (receiptObj == null) return;
        try {
            Class<?> cls = receiptObj.getClass();
            Field intField = null;
            Field jidField = null;

            for (Field f : cls.getDeclaredFields()) {
                f.setAccessible(true);
                if (f.getType() == int.class) {
                    intField = f;
                } else if (f.getType().getName().contains("Jid")) {
                    jidField = f;
                }
            }

            if (intField != null && jidField != null) {
                int receiptType = intField.getInt(receiptObj);
                Object jidVal = jidField.get(receiptObj);
                if (jidVal == null) return;
                String rawJid = jidVal.toString();

                // Type 13 = Read / Viewed status receipt
                if (receiptType == 13 && statusToast) {
                    emitToastWithThrottle(rawJid, "status", () -> {
                        String name = ContactNameResolver.INSTANCE.resolveName(context, rawJid, null, null);
                        return name + UiText.get(R.string.waex_ui_viewed_your_status_44b3e59c, " viewed your status");
                    });
                } else if ((receiptType == 13 || receiptType == 5) && msgToast) {
                    // Type 5 / 13 for read message receipt
                    emitToastWithThrottle(rawJid, "msg", () -> {
                        String name = ContactNameResolver.INSTANCE.resolveName(context, rawJid, null, null);
                        return name + UiText.get(R.string.waex_ui_viewed_your_message_1fbdce3c, " viewed your message");
                    });
                }
            }
        } catch (Throwable ignored) {}
    }

    private void emitToastWithThrottle(String rawJid, String actionKey, java.util.concurrent.Callable<String> messageBuilder) {
        String key = rawJid + "_" + actionKey;
        long now = System.currentTimeMillis();
        if (!TOAST_THROTTLE.shouldEmit(key, now)) return;

        asyncExecutor.execute(() -> {
            try {
                String message = messageBuilder.call();
                if (message != null && !message.isEmpty()) {
                    showToastSafely(message);
                }
            } catch (Throwable ignored) {}
        });
    }

    public static void showDeletedMessageToast(Context context, SharedPreferences prefs,
                                               String senderJid, Handler handler) {
        showDeletedToast(context, prefs, senderJid, handler, "message");
    }

    public static void showDeletedStatusToast(Context context, SharedPreferences prefs,
                                              String senderJid, Handler handler) {
        showDeletedToast(context, prefs, senderJid, handler, "status");
    }

    private static void showDeletedToast(Context context, SharedPreferences prefs,
                                         String senderJid, Handler handler, String subject) {
        if (context == null || prefs == null || handler == null) return;
        boolean enabled = prefs.getBoolean("toastdeleted", false);
        if (!enabled) return;

        String key = (senderJid != null ? senderJid : "unknown") + "_deleted_" + subject;
        long now = System.currentTimeMillis();
        if (!TOAST_THROTTLE.shouldEmit(key, now)) return;

        TOAST_EXECUTOR.execute(() -> {
            try {
                String name = senderJid != null
                        ? ContactNameResolver.INSTANCE.resolveName(context, senderJid, null, null)
                        : null;
                if (!ContactNameResolver.INSTANCE.isValidDisplayName(name)
                        || "Unknown".equalsIgnoreCase(name)) {
                    name = UiText.get(R.string.waex_ui_a_contact_f7f0de9a, "A contact");
                }
                String text = name + ("status".equals(subject)
                        ? UiText.get(R.string.waex_ui_deleted_a_status, " deleted a status")
                        : UiText.get(R.string.waex_ui_deleted_a_message_475dad17, " deleted a message"));
                handler.post(() -> {
                    try {
                        Toast.makeText(context, text, Toast.LENGTH_SHORT).show();
                    } catch (Throwable ignored) {}
                });
            } catch (Throwable ignored) {}
        });
    }

    private void showToastSafely(String message) {
        showToastSafely(message, () -> true);
    }

    private void showToastSafely(String message, java.util.function.BooleanSupplier stillValid) {
        mainHandler.post(() -> {
            try {
                // A queued name lookup must not announce an already invalidated transition.
                if (stillValid.getAsBoolean()) Toast.makeText(context, message, Toast.LENGTH_SHORT).show();
            } catch (Throwable ignored) {}
        });
    }

    private boolean isStatusViewedToastEnabled() {
        return isEnabled("toast_viewed_status", false);
    }

    private boolean isMessageViewedToastEnabled() {
        return isEnabled("toast_viewed_message", false);
    }

    private boolean isOnlineToastEnabled() {
        return isEnabled("showonline", false) || isEnabled("typing_online_toasts", false);
    }

    @NonNull
    @Override
    public String getName() {
        return "Presence Toasts";
    }
}
