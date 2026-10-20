package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Message;
import android.os.SystemClock;
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
import java.util.ArrayList;
import java.util.List;

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
    // Only an exact recipient + message ID may be exempted from read suppression.
    // A 120-second JID-wide bypass would leak unrelated receipts and override Ghost Mode.
    private static final RecipientReceiptAllowance EXPLICIT_RECEIPT_IDS =
            new RecipientReceiptAllowance(BLUE_REPLY_WINDOW_MS, 4096);

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
            XposedBridge.log(TAG + " Error initializing ProtocolTree reflection: " + t.getClass().getSimpleName());
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
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking enforce hiding: " + t.getClass().getSimpleName());
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
                                    && !hasExplicitReceiptIds(jid, param.args)) {
                                // The serialized job recipient is authoritative. A group participant
                                // or an arbitrary argument is not an alternate conversation identity.
                                String captureJid = canonicalJid(jid);
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
                            return;
                        }
                        // Never rewrite dispatcher type 89: SendReadReceiptJob waits for its
                        // acknowledgement. Cancel its verified execution body instead.
                        String target = resolveConversationTarget(jid, participant);
                        if (shouldHideDeliveryReceipt(target)) param.setResult(null);
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking SendReadReceiptJob: " + t.getClass().getSimpleName());
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

    private static boolean hasExplicitReceiptIds(String recipient, Object[] constructorArguments) {
        if (constructorArguments == null) return false;
        boolean foundIds = false;
        for (Object argument : constructorArguments) {
            if (!(argument instanceof String[])) continue;
            String[] ids = (String[]) argument;
            if (ids.length == 0) continue;
            foundIds = true;
            for (String id : ids) {
                if (!isExplicitReceiptAllowed(recipient, id)) return false;
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

                        String type = getAttributeValue(node, "type");
                        boolean isReadReceipt = "read".equals(type);
                        // A receipt node can also carry retry/recovery, own-device sync,
                        // played or future protocol messages. Only an ordinary delivery
                        // receipt (no type) or an explicit read receipt belongs to these
                        // two privacy controls. Preserve all other nodes and their sts.
                        if (type != null && !isReadReceipt) return;

                        String to = getAttributeValue(node, "to");
                        String participant = getAttributeValue(node, "participant");
                        String messageId = getAttributeValue(node, "id");

                        boolean isStatusStanza = isStatusTarget(to, participant);

                        if (isStatusStanza) {
                            // Status view receipts are suppressed via incoming interceptor and SendReadReceiptJob.
                            // Never return null here as WhatsApp requires a non-null ProtocolTreeNode instance.
                            return;
                        }

                        // Only explicit READ receipts may bypass hiding for the exact
                        // recipient + message ID. Preserve delivery hiding and Ghost Mode.
                        String target = resolveConversationTarget(to, participant);
                        boolean hideDelivery = shouldHideDeliveryReceipt(target);
                        if (ExplicitReadReceiptPolicy.maySend(type, target, messageId,
                                hideDelivery, EXPLICIT_RECEIPT_IDS,
                                SystemClock.elapsedRealtime())) return;
                        boolean hideRead = isReadReceipt && shouldHideReadReceipt(target);

                        if (hideDelivery) {
                            applyHideDelivery(node);
                        } else if (hideRead) {
                            applyHideRead(node);
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking receipt method: " + t.getClass().getSimpleName());
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
            XposedBridge.log(TAG + " Error hooking delivery dispatchers: " + t.getClass().getSimpleName());
        }
    }

    /**
     * Hook onDispatchMessage for delivery/read suppression.
     *
     * Type 89 belongs to SendReadReceiptJob. Rewriting it prevents the job's
     * acknowledgement future from completing and can stall WhatsApp's job queue.
     * Job suppression must happen in the verified execution hook above instead.
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
                            if (isHideDeliveryReceiptsEnabled() && msg.arg1 == 419) {
                                msg.arg1 = -1; // Cancel only the ordinary receipt dispatcher.
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking onDispatchMessage: " + t.getClass().getSimpleName());
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
            XposedBridge.log(TAG + " Error applying hide delivery: " + t.getClass().getSimpleName());
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
            XposedBridge.log(TAG + " Error applying hide read: " + t.getClass().getSimpleName());
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
        // Numeric broadcast-list recipients are ordinary conversations. Matching
        // the namespace or a substring would apply status privacy to their jobs.
        return "status@broadcast".equals(jid) || "status@broadcast".equals(participant);
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

    /**
     * Stage exactly the message IDs scheduled for one recipient.
     * Must be called before constructing the read job, because its constructor
     * is hooked; failed enqueue attempts must revoke these tentative grants.
     */
    public static void allowExplicitReceiptIds(String recipient, Object[] constructorArguments) {
        String key = canonicalJid(recipient);
        if (key == null || constructorArguments == null) return;
        long now = SystemClock.elapsedRealtime();
        for (Object argument : constructorArguments) {
            if (!(argument instanceof String[])) continue;
            for (String messageId : (String[]) argument) {
                EXPLICIT_RECEIPT_IDS.allow(key, messageId, now);
            }
        }
    }

    /** Revoke tentative permissions when the explicit receipt could not be enqueued. */
    public static void revokeExplicitReceiptIds(String recipient, Object[] constructorArguments) {
        String key = canonicalJid(recipient);
        if (key == null || constructorArguments == null) return;
        for (Object argument : constructorArguments) {
            if (!(argument instanceof String[])) continue;
            for (String messageId : (String[]) argument) {
                EXPLICIT_RECEIPT_IDS.revoke(key, messageId);
            }
        }
    }

    private static boolean isExplicitReceiptAllowed(String recipient, String messageId) {
        return EXPLICIT_RECEIPT_IDS.isAllowed(canonicalJid(recipient), messageId,
                SystemClock.elapsedRealtime());
    }

    private static String canonicalJid(String value) {
        return ReceiptJidPolicy.canonical(value);
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
            Method dispatch = resolvePlayedReceiptDispatch();
            if (dispatch == null) {
                XposedBridge.log(TAG + " WARNING: Verified played dispatcher unavailable; audio/view-once privacy coverage is incomplete.");
                return;
            }
            XposedBridge.hookMethod(dispatch, new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    if (!PlayedReceiptDispatchPolicy.isDispatchCall(
                            dispatch, param.method, param.thisObject, param.args)) return;
                    java.util.Set<?> messages = (java.util.Set<?>) param.args[0];
                    // Retain existing played-batch privacy semantics. Media-kind classification
                    // and mixed-batch granularity require an independently verified contract.
                    if (!messages.isEmpty()
                            && shouldSuppressPlayedReceipt(messages.iterator().next())) {
                        param.setResult(null);
                    }
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Error hooking sender played: " + t.getClass().getSimpleName());
        }
    }

    private Method resolvePlayedReceiptDispatch() {
        Method method = DexSearchEngine.getInstance().findMethodWithCache(
                context, classLoader, "wpp_played_batch_dispatch_v1",
                (bridge, loader) -> {
                    // sendClearDirty identifies a multi-purpose dispatcher, not a played method.
                    // Require the actual constructor call edge observed for the receipt job.
                    MethodDataList matches = bridge.findMethod(FindMethod.create()
                            .matcher(MethodMatcher.create()
                                    .returnType("void")
                                    .paramCount(2)
                                    .addParamType("java.util.Set")
                                    .addParamType("boolean")
                                    .addInvoke(MethodMatcher.create()
                                            .declaredClass("com.whatsapp.messaging.receipts.jobqueue.job.SendPlayedReceiptJobV2")
                                            .name("<init>")
                                            .paramCount(2)
                                            .addUsingString("played-receipt-v2-", StringMatchType.Equals))));
                    if (matches.size() != 1) return null;
                    Method candidate = matches.get(0).getMethodInstance(loader);
                    return PlayedReceiptDispatchPolicy.isDispatchMethod(candidate) ? candidate : null;
                });
        return PlayedReceiptDispatchPolicy.isDispatchMethod(method) ? method : null;
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
