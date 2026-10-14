package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Message;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import org.json.JSONObject;
import org.luckypray.dexkit.query.FindClass;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.ClassMatcher;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.ClassData;
import org.luckypray.dexkit.result.ClassDataList;
import org.luckypray.dexkit.result.MethodData;
import org.luckypray.dexkit.result.MethodDataList;
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Privacy Receipts Hook:
 * Handles privacy controls for outgoing receipts:
 * 1. Read Receipts (Blue Ticks) - `hide_read_receipts`: Drops incoming read receipt dispatchers, SendReadReceiptJob & strips "type=read" on receipt stanzas.
 * 2. Delivery Receipts (Second Tick) - `hide_delivery_receipts`: Suppresses delivery dispatchers, modifies receipt stanza to "type=inactive", and intercepts connection writer dispatch.
 * 3. Stealth Status Viewing - `stealth_status_view` / per-contact `HideViewStatus`: Suppresses status viewed receipt jobs, incoming dispatchers, and stanzas.
 */
public class HideReceiptsHook extends BaseFeature {

    private static final String TAG = "[WAEX][HideReceipts]";
    private static final long BLUE_REPLY_WINDOW_MS = 120_000L;
    private static final Pattern JID_PATTERN = Pattern.compile(
            "([0-9-]+)@(s\\.whatsapp\\.net|g\\.us|lid|broadcast)");
    private static final Map<String, Long> BLUE_REPLY_BYPASS = new ConcurrentHashMap<>();
    private static final Map<String, Long> EXPLICIT_RECEIPT_IDS = new ConcurrentHashMap<>();

    private Class<?> protocolTreeNodeClass;
    private Class<?> keyValueClass;
    private Field fieldAttributes;
    private Field fieldKey;
    private Field fieldValue;
    private Constructor<?> keyValueStringConstructor;

    public HideReceiptsHook(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override
    public void hook() throws Throwable {
        initProtocolTreeReflection();
        hookEnforceHiding();
        hookSendReadReceiptJob();
        hookReceiptMethod();
        hookDeliveryDispatchers();
        hookOnDispatchMessage();
        hookSenderPlayed();
    }

    private void initProtocolTreeReflection() {
        try {
            protocolTreeNodeClass = DexSearchEngine.getInstance().findClassWithCache(
                    context,
                    classLoader,
                    "wpp_protocol_tree_node_class",
                    (bridge, loader) -> {
                        ClassData cd = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create().usingStrings("ProtocolTreeNode/getAttributeJid"))
                        ).firstOrNull();
                        return cd != null ? cd.getInstance(loader) : null;
                    }
            );

            keyValueClass = DexSearchEngine.getInstance().findClassWithCache(
                    context,
                    classLoader,
                    "wpp_key_value_class",
                    (bridge, loader) -> {
                        ClassData cd = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create().usingStrings("KeyValue{key="))
                        ).firstOrNull();
                        return cd != null ? cd.getInstance(loader) : null;
                    }
            );

            if (protocolTreeNodeClass != null && keyValueClass != null) {
                Class<?> keyValueArrayType = Array.newInstance(keyValueClass, 0).getClass();
                for (Field f : protocolTreeNodeClass.getDeclaredFields()) {
                    if (f.getType() == keyValueArrayType) {
                        fieldAttributes = f;
                        fieldAttributes.setAccessible(true);
                        break;
                    }
                }

                List<Field> strFields = new ArrayList<>();
                for (Field f : keyValueClass.getDeclaredFields()) {
                    if (f.getType() == String.class) {
                        f.setAccessible(true);
                        strFields.add(f);
                    }
                }
                if (strFields.size() >= 2) {
                    fieldKey = strFields.get(0);
                    fieldValue = strFields.get(1);
                }

                for (Constructor<?> c : keyValueClass.getDeclaredConstructors()) {
                    Class<?>[] params = c.getParameterTypes();
                    if (params.length == 2 && params[0] == String.class && params[1] == String.class) {
                        keyValueStringConstructor = c;
                        keyValueStringConstructor.setAccessible(true);
                        break;
                    }
                }
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error initializing ProtocolTree reflection: " + t.getMessage());
        }
    }

    /**
     * Enforce suppression at the root incoming receipt method.
     * Hooks ReadReceipts/sendReceiptForIncomingMessage to prevent status or message read receipts from ever generating.
     */
    private void hookEnforceHiding() {
        try {
            Method readReceiptMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_read_receipt_incoming_message",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("ReadReceipts/sendReceiptForIncomingMessage", StringMatchType.Contains))
                        ).firstOrNull();
                        return md != null ? md.getMethodInstance(loader) : null;
                    }
            );

            if (readReceiptMethod != null) {
                XposedBridge.hookMethod(readReceiptMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (param.args == null || param.args.length == 0) return;
                        Object fMessageObj = param.args[0];
                        if (fMessageObj == null) return;

                        String jid = extractJidString(fMessageObj, "key");
                        String participant = extractParticipantOrJid(fMessageObj);
                        String target = resolveConversationTarget(jid, participant);

                        if (isStatusTarget(jid, participant)) {
                            if (shouldHideStatusView(target)) {
                                param.setResult(null);
                            }
                            return;
                        }

                        if (shouldHideReadReceipt(target)) {
                            // Do not cancel this call. On current WhatsApp builds the open-chat
                            // path may combine delivery and read acknowledgement generation. The
                            // ProtocolTreeNode hook below downgrades only type=read, preserving the
                            // sender's ordinary delivered (double-tick) acknowledgement.
                            XposedBridge.log(TAG + " EnforceHiding: Downgrading read receipt for " + target);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking enforce hiding: " + t.getMessage());
        }
    }

    /**
     * Hook SendReadReceiptJob to suppress outgoing blue read ticks and stealth status view receipts.
     */
    private void hookSendReadReceiptJob() {
        try {
            Class<?> sendJobClass = null;
            try {
                sendJobClass = XposedHelpers.findClassIfExists(
                        "com.whatsapp.messaging.receipts.jobqueue.job.SendReadReceiptJob", classLoader);
                if (sendJobClass == null) {
                    sendJobClass = XposedHelpers.findClassIfExists(
                            "com.whatsapp.jobqueue.job.SendReadReceiptJob", classLoader);
                }
            } catch (Throwable ignored) {}

            if (sendJobClass == null) {
                sendJobClass = DexSearchEngine.getInstance().findClassWithCache(
                        context,
                        classLoader,
                        "wpp_send_read_receipt_job_class",
                        (bridge, loader) -> {
                            ClassData cd = bridge.findClass(FindClass.create()
                                    .matcher(ClassMatcher.create().className("SendReadReceiptJob", StringMatchType.EndsWith))
                            ).firstOrNull();
                            return cd != null ? cd.getInstance(loader) : null;
                        }
                );
            }

            if (sendJobClass != null) {
                // Hook all constructors to detect status read jobs
                XposedBridge.hookAllConstructors(sendJobClass, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        try {
                            Object job = param.thisObject;
                            String jid = extractJidString(job, "jid");
                            String participant = extractJidString(job, "participant");
                            if (isStatusTarget(jid, participant)) {
                                String target = (participant != null && !participant.contains("@broadcast")) ? participant : jid;
                                if (shouldHideStatusView(target)) {
                                    XposedHelpers.setAdditionalInstanceField(job, "waex_hide_status_view", true);
                                }
                            } else if ((isEnabled("blueonreply", false)
                                    || isManualSeenTickEnabled())
                                    && !hasExplicitReceiptIds(param.args)) {
                                String captureJid = jid != null ? jid : participant;
                                if (captureJid == null) {
                                    captureJid = findJidInObject(job);
                                }
                                if (captureJid == null) {
                                    captureJid = findJidInArguments(param.args);
                                }
                                if (captureJid != null) {
                                    BlueOnReplyHook.captureSuppressedReadJob(
                                            captureJid, (Constructor<?>) param.method, param.args);
                                }
                            }
                        } catch (Throwable ignored) {}
                    }
                });

                // A job also declares retry, initialization and serialization methods.
                // Suppress only its uniquely identified execution body, never every method.
                final Class<?> resolvedJobClass = sendJobClass;
                final Method executionMethod = resolveReadReceiptExecution(resolvedJobClass);
                if (executionMethod == null) {
                    XposedBridge.log(TAG + " Status receipt execution contract unavailable; job privacy coverage incomplete");
                    return;
                }
                XposedBridge.hookMethod(executionMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (!ReceiptJobExecutionPolicy.isExecutionCall(
                                resolvedJobClass, executionMethod, param.method,
                                param.thisObject, param.args)) return;
                        Object job = param.thisObject;
                        if (Boolean.TRUE.equals(XposedHelpers.getAdditionalInstanceField(
                                job, "waex_hide_status_view"))) {
                            param.setResult(null);
                            return;
                        }
                        String jid = extractJidString(job, "jid");
                        String participant = extractJidString(job, "participant");
                        if (isStatusTarget(jid, participant)) {
                            String target = participant != null && !participant.contains("@broadcast")
                                    ? participant : jid;
                            if (shouldHideStatusView(target)) param.setResult(null);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking SendReadReceiptJob: " + t.getMessage());
        }
    }

    private Method resolveReadReceiptExecution(final Class<?> jobClass) {
        Method method = DexSearchEngine.getInstance().findMethodWithCache(
                context, classLoader, "wpp_send_read_receipt_execution_v1",
                (bridge, loader) -> {
                    // The reviewed 2.26.39.79 body builds a "receipt" stanza and
                    // handles receiptClass="status". No obfuscated method name is pinned.
                    MethodDataList matches = bridge.findMethod(FindMethod.create()
                            .matcher(MethodMatcher.create()
                                    .declaredClass(jobClass.getName())
                                    .paramCount(0)
                                    .returnType("void")
                                    .addUsingString("receipt", StringMatchType.Equals)
                                    .addUsingString("status", StringMatchType.Equals)));
                    if (matches.size() != 1) return null;
                    Method candidate = matches.get(0).getMethodInstance(loader);
                    return ReceiptJobExecutionPolicy.isExecutionMethod(jobClass, candidate)
                            ? candidate : null;
                });
        // Revalidate descriptors restored from the positive cache as well.
        return ReceiptJobExecutionPolicy.isExecutionMethod(jobClass, method) ? method : null;
    }

    private boolean isManualSeenTickEnabled() {
        if (!isHideReadReceiptsEnabled()) return false;
        Object value = prefs.getAll().get("seentick");
        if (value instanceof Boolean) return (Boolean) value;
        if (value instanceof Number) return ((Number) value).intValue() != 0;
        if (value instanceof String) {
            String text = (String) value;
            return !text.isEmpty() && !"0".equals(text)
                    && !"false".equalsIgnoreCase(text);
        }
        return false;
    }

    private static String findJidInObject(Object obj) {
        if (obj == null) return null;
        try {
            Class<?> curr = obj.getClass();
            while (curr != null && curr != Object.class) {
                for (Field f : curr.getDeclaredFields()) {
                    if (Modifier.isStatic(f.getModifiers())) continue;
                    f.setAccessible(true);
                    Object val = f.get(obj);
                    if (val == null) continue;
                    String s = val.toString();
                    String jid = canonicalJid(s);
                    if (jid != null) return jid;
                }
                curr = curr.getSuperclass();
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static String findJidInArguments(Object[] arguments) {
        if (arguments == null) return null;
        for (Object argument : arguments) {
            if (argument == null || argument instanceof String[]) continue;
            String value = String.valueOf(argument);
            String jid = canonicalJid(value);
            if (jid != null) return jid;
        }
        return null;
    }

    private static boolean hasExplicitReceiptIds(Object[] constructorArguments) {
        if (constructorArguments == null) return false;
        boolean foundIds = false;
        for (Object argument : constructorArguments) {
            if (!(argument instanceof String[])) continue;
            String[] ids = (String[]) argument;
            if (ids.length == 0) continue;
            foundIds = true;
            for (String id : ids) {
                if (!isExplicitReceiptAllowed(id)) return false;
            }
        }
        return foundIds;
    }

    /**
     * Hook receipt stanza generator method (ProtocolTreeNode).
     */
    private void hookReceiptMethod() {
        try {
            Method receiptMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_receipt_node_generator",
                    (bridge, loader) -> {
                        ClassData classDeviceJid = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create().className("jid.DeviceJid", StringMatchType.EndsWith))).firstOrNull();

                        ClassData classNode = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create().usingStrings("ProtocolTreeNode/getAttributeJid"))).firstOrNull();

                        if (classDeviceJid != null && classNode != null) {
                            MethodDataList methods = bridge.findMethod(FindMethod.create()
                                    .matcher(MethodMatcher.create()
                                            .addUsingString("receipt", StringMatchType.Contains)
                                            .returnType(classNode.getName())
                                    ));
                            for (MethodData md : methods) {
                                if (md.getParamTypeNames().contains(classDeviceJid.getName())) {
                                    return md.getMethodInstance(loader);
                                }
                            }
                        }
                        return null;
                    }
            );

            if (receiptMethod != null) {
                XposedBridge.hookMethod(receiptMethod, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.getResult() == null) return;
                        Object node = param.getResult();

                        String to = getAttributeValue(node, "to");
                        String participant = getAttributeValue(node, "participant");
                        String type = getAttributeValue(node, "type");
                        String messageId = getAttributeValue(node, "id");

                        // Manual/Blue-on-Reply jobs authorize exact message IDs. This survives
                        // phone-JID/LID/device-JID differences between receive and send paths.
                        if (isExplicitReceiptAllowed(messageId)) return;

                        boolean isStatusStanza = isStatusTarget(to, participant) || "readstatus".equals(type);

                        if (isStatusStanza) {
                            // Status view receipts are suppressed via incoming interceptor and SendReadReceiptJob.
                            // Never return null here as WhatsApp requires a non-null ProtocolTreeNode instance.
                            return;
                        }

                        String target = participant != null ? participant : to;
                        boolean hideDelivery = shouldHideDeliveryReceipt(target);
                        boolean hideRead = shouldHideReadReceipt(target);

                        if (hideDelivery) {
                            applyHideDelivery(node);
                        } else if (hideRead) {
                            applyHideRead(node);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking receipt method: " + t.getMessage());
        }
    }

    /**
     * Hooks delivery dispatchers to suppress delivery receipts when hide_delivery_receipts is enabled.
     */
    private void hookDeliveryDispatchers() {
        try {
            String[] deliveryAnchors = new String[]{
                    "ReadReceipts/sendDeliveryReadReceipt",
                    "ReadReceipts/sendDeliveryReceiptIfNotRetry"
            };

            for (String anchor : deliveryAnchors) {
                Method deliveryMethod = DexSearchEngine.getInstance().findMethodWithCache(
                        context,
                        classLoader,
                        "wpp_delivery_anchor_" + anchor.replace('/', '_'),
                        (bridge, loader) -> {
                            MethodData md = bridge.findMethod(FindMethod.create()
                                    .matcher(MethodMatcher.create().addUsingString(anchor, StringMatchType.Contains))
                            ).firstOrNull();
                            return md != null ? md.getMethodInstance(loader) : null;
                        }
                );

                if (deliveryMethod != null) {
                    XposedBridge.hookMethod(deliveryMethod, new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            if (isHideDeliveryReceiptsEnabled()) {
                                param.setResult(null); // Drop delivery receipt dispatch
                            }
                        }
                    });
                }
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking delivery dispatchers: " + t.getMessage());
        }
    }

    /**
     * Hook onDispatchMessage (type 419 / 89) for delivery/read suppression.
     */
    private void hookOnDispatchMessage() {
        try {
            Method dispatchMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "wpp_on_dispatch_message_419",
                    (bridge, loader) -> {
                        MethodDataList methods = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("ConnectionWriter/sendReadReceipts", StringMatchType.Contains)
                                        .paramCount(1, 5)
                                ));
                        for (MethodData md : methods) {
                            if (!md.getParamTypeNames().isEmpty() && md.getParamTypeNames().get(0).contains("Message")) {
                                return md.getMethodInstance(loader);
                            }
                        }
                        return null;
                    }
            );

            if (dispatchMethod != null) {
                XposedBridge.hookMethod(dispatchMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (param.args.length > 0 && param.args[0] instanceof Message) {
                            Message msg = (Message) param.args[0];
                            if (isHideDeliveryReceiptsEnabled()) {
                                if (msg.arg1 == 419 || msg.arg1 == 89) {
                                    msg.arg1 = -1; // Change/cancel type
                                }
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking onDispatchMessage: " + t.getMessage());
        }
    }

    /**
     * Replaces receipt attributes to have type="inactive" and removes "sts",
     * preventing WhatsApp server from acknowledging delivery to sender.
     */
    private void applyHideDelivery(Object node) {
        if (fieldAttributes == null || keyValueStringConstructor == null) return;
        try {
            Object[] currentAttrs = (Object[]) fieldAttributes.get(node);
            List<Object> newAttrList = new ArrayList<>();
            boolean addedType = false;

            if (currentAttrs != null) {
                for (Object kv : currentAttrs) {
                    if (kv == null) continue;
                    String key = getKey(kv);
                    if ("sts".equals(key)) {
                        continue; // Remove sts
                    }
                    if ("type".equals(key)) {
                        Object inactiveKv = keyValueStringConstructor.newInstance("type", "inactive");
                        newAttrList.add(inactiveKv);
                        addedType = true;
                    } else {
                        newAttrList.add(kv);
                    }
                }
            }

            if (!addedType) {
                Object inactiveKv = keyValueStringConstructor.newInstance("type", "inactive");
                newAttrList.add(inactiveKv);
            }

            Object newArray = Array.newInstance(keyValueClass, newAttrList.size());
            for (int i = 0; i < newAttrList.size(); i++) {
                Array.set(newArray, i, newAttrList.get(i));
            }
            fieldAttributes.set(node, newArray);
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error applying hide delivery: " + t.getMessage());
        }
    }

    /**
     * Strips "type=read" and "sts" attributes so the receipt passes as normal delivery confirmation.
     */
    private void applyHideRead(Object node) {
        if (fieldAttributes == null) return;
        try {
            Object[] currentAttrs = (Object[]) fieldAttributes.get(node);
            if (currentAttrs == null) return;

            List<Object> newAttrList = new ArrayList<>();
            boolean modified = false;

            for (Object kv : currentAttrs) {
                if (kv == null) continue;
                String key = getKey(kv);
                String val = getValue(kv);
                if ("sts".equals(key)) {
                    modified = true;
                    continue;
                }
                if ("type".equals(key) && "read".equals(val)) {
                    modified = true;
                    continue;
                }
                newAttrList.add(kv);
            }

            if (modified) {
                Object newArray = Array.newInstance(keyValueClass, newAttrList.size());
                for (int i = 0; i < newAttrList.size(); i++) {
                    Array.set(newArray, i, newAttrList.get(i));
                }
                fieldAttributes.set(node, newArray);
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error applying hide read: " + t.getMessage());
        }
    }

    private String getKey(Object kv) {
        if (fieldKey != null) {
            try {
                return (String) fieldKey.get(kv);
            } catch (Throwable ignored) {}
        }
        return null;
    }

    private String getValue(Object kv) {
        if (fieldValue != null) {
            try {
                return (String) fieldValue.get(kv);
            } catch (Throwable ignored) {}
        }
        return null;
    }

    private String getAttributeValue(Object node, String targetKey) {
        if (fieldAttributes == null || node == null) return null;
        try {
            Object[] currentAttrs = (Object[]) fieldAttributes.get(node);
            if (currentAttrs == null) return null;
            for (Object kv : currentAttrs) {
                if (kv == null) continue;
                String key = getKey(kv);
                if (targetKey.equals(key)) {
                    return getValue(kv);
                }
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private String extractJidString(Object obj, String fieldName) {
        if (obj == null || fieldName == null) return null;
        try {
            Object fieldVal = XposedHelpers.getObjectField(obj, fieldName);
            if (fieldVal == null) return null;
            if (fieldVal instanceof String) {
                return (String) fieldVal;
            }
            try {
                Object raw = XposedHelpers.callMethod(fieldVal, "getRawString");
                if (raw != null) return raw.toString();
            } catch (Throwable ignored) {}
            return fieldVal.toString();
        } catch (Throwable ignored) {
            return null;
        }
    }

    private String extractParticipantOrJid(Object fMessageObj) {
        if (fMessageObj == null) return null;
        try {
            Class<?> curr = fMessageObj.getClass();
            while (curr != null && curr != Object.class) {
                for (Field f : curr.getDeclaredFields()) {
                    f.setAccessible(true);
                    Object val = f.get(fMessageObj);
                    if (val != null) {
                        String s = val.toString();
                        if (s.contains("@s.whatsapp.net") || s.contains("@lid") || s.contains("@broadcast")) {
                            return s;
                        }
                    }
                }
                curr = curr.getSuperclass();
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private boolean isStatusTarget(String jid, String participant) {
        if (jid != null && (jid.equals("status@broadcast") || jid.contains("status") || jid.contains("broadcast"))) {
            return true;
        }
        if (participant != null && (participant.contains("status") || participant.contains("broadcast"))) {
            return true;
        }
        return false;
    }

    private boolean shouldHideStatusView(String target) {
        boolean globalEnabled = isStealthStatusViewEnabled();
        if (target != null) {
            JSONObject contactPrivacy = CustomPrivacyHook.getContactPrivacy(prefs, target);
            if (contactPrivacy != null) {
                return contactPrivacy.optBoolean("HideViewStatus", globalEnabled);
            }
        }
        return globalEnabled;
    }

    private boolean shouldHideReadReceipt(String target) {
        if (isBlueReplyBypassed(target)) {
            return false;
        }
        if (isGhostModeActive()) {
            return true;
        }
        boolean isGroup = target != null && (target.contains("@g.us") || target.contains("-"));
        boolean globalEnabled = isGroup ? isEnabled("hideread_group", false) : isHideReadReceiptsEnabled();
        if (target != null) {
            JSONObject contactPrivacy = CustomPrivacyHook.getContactPrivacy(prefs, target);
            if (contactPrivacy != null) {
                return contactPrivacy.optBoolean("HideSeen", globalEnabled);
            }
        }
        return globalEnabled;
    }

    private boolean shouldHideDeliveryReceipt(String target) {
        if (isGhostModeActive()) return true;
        boolean globalEnabled = isEnabled("hide_delivery_receipts", false)
                || isEnabled("hidereceipt", false);
        if (target != null) {
            JSONObject contactPrivacy = CustomPrivacyHook.getContactPrivacy(prefs, target);
            if (contactPrivacy != null) {
                return contactPrivacy.optBoolean("HideReceipt", globalEnabled);
            }
        }
        return globalEnabled;
    }

    /** Temporarily permits an explicit read-receipt job created by Blue-on-Reply. */
    public static void allowBlueReplyReceipt(String jid) {
        String key = canonicalJid(jid);
        if (key == null) return;
        BLUE_REPLY_BYPASS.put(key, System.currentTimeMillis() + BLUE_REPLY_WINDOW_MS);
    }

    public static void allowExplicitReceiptIds(Object[] constructorArguments) {
        if (constructorArguments == null) return;
        long expiresAt = System.currentTimeMillis() + BLUE_REPLY_WINDOW_MS;
        for (Object argument : constructorArguments) {
            if (!(argument instanceof String[])) continue;
            for (String messageId : (String[]) argument) {
                if (messageId != null && !messageId.isEmpty()) {
                    EXPLICIT_RECEIPT_IDS.put(messageId, expiresAt);
                }
            }
        }
    }

    private static boolean isExplicitReceiptAllowed(String messageId) {
        if (messageId == null) return false;
        Long expiresAt = EXPLICIT_RECEIPT_IDS.get(messageId);
        if (expiresAt == null) return false;
        if (expiresAt >= System.currentTimeMillis()) return true;
        EXPLICIT_RECEIPT_IDS.remove(messageId, expiresAt);
        return false;
    }

    private static boolean isBlueReplyBypassed(String jid) {
        String key = canonicalJid(jid);
        if (key == null) return false;
        Long expiresAt = BLUE_REPLY_BYPASS.get(key);
        if (expiresAt == null) return false;
        if (expiresAt >= System.currentTimeMillis()) return true;
        BLUE_REPLY_BYPASS.remove(key, expiresAt);
        return false;
    }

    private static String canonicalJid(String value) {
        if (value == null) return null;
        Matcher matcher = JID_PATTERN.matcher(value);
        return matcher.find() ? matcher.group(1) + "@" + matcher.group(2) : null;
    }

    /** Prefer the conversation/group address over a group participant's device address. */
    private static String resolveConversationTarget(String keyValue, String participantValue) {
        String keyJid = canonicalJid(keyValue);
        String participantJid = canonicalJid(participantValue);
        if (keyJid != null && (keyJid.endsWith("@g.us") || keyJid.endsWith("@broadcast"))) {
            return keyJid;
        }
        if (participantJid != null
                && (participantJid.endsWith("@g.us") || participantJid.endsWith("@broadcast"))) {
            return participantJid;
        }
        return keyJid != null ? keyJid : participantJid;
    }

    /**
     * Hooks WhatsApp's SenderPlayed dispatcher to suppress outgoing "Played" / "Opened" receipts
     * for Voice Notes (audio) and View-Once media when the corresponding privacy toggles are active.
     */
    private void hookSenderPlayed() {
        try {
            DexSearchEngine engine = DexSearchEngine.getInstance();

            // 1. Resolve SenderPlayed class via anchor string
            Class<?> senderPlayedClass = engine.findClassWithCache(
                    context,
                    classLoader,
                    "wpp_sender_played_class",
                    (bridge, loader) -> {
                        ClassData cd = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create().usingStrings("sendmethods/sendClearDirty"))
                        ).firstOrNull();
                        return cd != null ? cd.getInstance(loader) : null;
                    }
            );

            if (senderPlayedClass == null) {
                XposedBridge.log(TAG + " WARNING: SenderPlayed class not found.");
                return;
            }

            // 2. Hook single-message played sender method
            for (Method m : senderPlayedClass.getDeclaredMethods()) {
                if (m.getParameterCount() == 1) {
                    Class<?> pType = m.getParameterTypes()[0];
                    // Parameter is FMessage or media message type
                    if (!pType.isPrimitive() && !pType.getName().startsWith("java.lang.")) {
                        XposedBridge.hookMethod(m, new XC_MethodHook() {
                            @Override
                            protected void beforeHookedMethod(MethodHookParam param) {
                                Object msgObj = param.args[0];
                                if (shouldSuppressPlayedReceipt(msgObj)) {
                                    param.setResult(null);
                                }
                            }
                        });
                    }
                } else if (m.getParameterCount() > 0 && java.util.Set.class.isAssignableFrom(m.getParameterTypes()[0])) {
                    // Hook batch/business set played sender method
                    XposedBridge.hookMethod(m, new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            if (param.args[0] instanceof java.util.Set) {
                                java.util.Set<?> set = (java.util.Set<?>) param.args[0];
                                if (!set.isEmpty()) {
                                    Object first = set.iterator().next();
                                    if (shouldSuppressPlayedReceipt(first)) {
                                        param.setResult(null);
                                    }
                                }
                            }
                        }
                    });
                }
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking sender played: " + t.getMessage());
        }
    }

    private boolean shouldSuppressPlayedReceipt(Object msgObj) {
        if (msgObj == null) return false;

        boolean hideVoiceNote = isHideVoiceNotePlayedEnabled();
        boolean hideViewOnce = isHideViewOnceSeenEnabled();

        if (!hideVoiceNote && !hideViewOnce) return false;

        try {
            // Check media type / view once properties dynamically
            Class<?> cls = msgObj.getClass();
            while (cls != null && cls != Object.class) {
                for (Field f : cls.getDeclaredFields()) {
                    f.setAccessible(true);
                    String name = f.getName().toLowerCase();
                    if (f.getType() == int.class || f.getType() == byte.class) {
                        int val = f.getInt(msgObj);
                        // MediaType 2 = Voice Note / Audio
                        if (hideVoiceNote && val == 2) {
                            return true;
                        }
                    } else if (f.getType() == boolean.class) {
                        boolean bVal = f.getBoolean(msgObj);
                        if (hideViewOnce && (name.contains("viewonce") || name.contains("ephemeral")) && bVal) {
                            return true;
                        }
                    }
                }
                cls = cls.getSuperclass();
            }
        } catch (Throwable ignored) {}

        // Fallback: If either toggle is enabled and played method is triggered for this message
        return hideVoiceNote || hideViewOnce;
    }

    private boolean isGhostModeActive() {
        return isEnabled("ghostmode_active", false);
    }

    private boolean isHideVoiceNotePlayedEnabled() {
        return isEnabled("hide_seen_receipts", false) || isEnabled("hideaudioseen", false) || isGhostModeActive();
    }

    private boolean isHideViewOnceSeenEnabled() {
        return isEnabled("hideonceseen", false) || isGhostModeActive();
    }

    private boolean isHideReadReceiptsEnabled() {
        return isEnabled("hide_read_receipts", false) || isEnabled("hideread", false) || isGhostModeActive();
    }

    private boolean isHideDeliveryReceiptsEnabled() {
        return isEnabled("hide_delivery_receipts", false) || isEnabled("hidereceipt", false) || isGhostModeActive();
    }

    private boolean isStealthStatusViewEnabled() {
        if (isGhostModeActive()) {
            return true;
        }
        try {
            if (prefs.contains("stealth_status_view")) {
                Object val = prefs.getAll().get("stealth_status_view");
                if (val instanceof Boolean) return (Boolean) val;
                if (val instanceof String) return !"0".equals(val) && !"false".equalsIgnoreCase((String) val);
                if (val instanceof Number) return ((Number) val).intValue() != 0;
            }
            if (prefs.contains("hidestatusview")) {
                Object val = prefs.getAll().get("hidestatusview");
                if (val instanceof Boolean) return (Boolean) val;
                if (val instanceof String) return !"0".equals(val) && !"false".equalsIgnoreCase((String) val);
                if (val instanceof Number) return ((Number) val).intValue() != 0;
            }
        } catch (Throwable ignored) {}
        return isEnabled("stealth_status_view", false) || isEnabled("hidestatusview", false);
    }

    @NonNull
    @Override
    public String getName() {
        return "Hide Receipts";
    }
}
