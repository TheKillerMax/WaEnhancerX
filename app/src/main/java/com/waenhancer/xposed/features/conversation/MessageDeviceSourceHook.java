package com.waenhancer.xposed.features.conversation;

import com.waenhancer.utils.UiText;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.widget.HeaderViewListAdapter;
import android.widget.ListAdapter;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.waenhancer.app.R;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.db.MessageDeviceSourceStore;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.utils.ActivityTracker;

import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.MethodData;

import java.lang.ref.WeakReference;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.function.Consumer;
import java.util.regex.Pattern;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import org.luckypray.dexkit.query.FindClass;
import org.luckypray.dexkit.query.matchers.ClassMatcher;

/**
 * Message Device Source Feature for WhatsApp.
 *
 * Shows whether a received message was sent from a Primary phone (📱) or a Linked device (💻).
 * Clicking the device icon displays an informative Toast.
 */
public class MessageDeviceSourceHook extends BaseFeature {

    public static final String PREF_KEY = "message_device_source";
    private static final String TAG = "[WAEX][DeviceSource]";

    private static final String PRIMARY_DEVICE_EMOJI = " \uD83D\uDCF1";
    private static final String LINKED_DEVICE_EMOJI = " \uD83D\uDCBB";

    private static final String FIELD_DEVICE_SUFFIX = "wae_device_source_suffix";
    private static final String FIELD_DEVICE_GUARD = "wae_device_source_guard";
    private static final String FIELD_DEVICE_MSG_ID = "wae_device_source_message_id";
    private static final String FIELD_DEVICE_ROW_BINDING = "wae_device_source_row_binding";
    private static final String FIELD_DEVICE_CLICK_LISTENER = "wae_device_source_click_listener";
    private static final String FIELD_DEVICE_ORIGINAL_TEXT = "wae_device_source_original_text";
    private static final String FIELD_DEVICE_RENDERED_TEXT = "wae_device_source_rendered_text";

    private static volatile Field sDeviceListenerInfoField;
    private static volatile Field sDeviceOnClickListenerField;

    /** Owned by the row, including views detached during an adapter rebind. */
    private static final class DeviceSourceRowBinding {
        volatile boolean active = true;
        WeakReference<TextView> anchor;
        // Xposed's additional-instance-field values are held by a global weak-key
        // table. A strong view reference here would keep its own weak key alive
        // through row -> binding -> target -> parent row.
        final List<WeakReference<TextView>> targets = new ArrayList<>();
    }

    private static volatile boolean conversationActive = false;
    private final Set<Class<?>> hookedAdapterClasses = Collections.newSetFromMap(new ConcurrentHashMap<>());
    private static Class<?> fMessageClass;
    private static Class<?> deviceJidClass;

    private static final Executor UI_EXECUTOR = action -> {
        Handler handler = new Handler(Looper.getMainLooper());
        handler.post(action);
    };

    public MessageDeviceSourceHook(
            @NonNull Context context,
            @NonNull ClassLoader classLoader,
            @NonNull SharedPreferences prefs
    ) {
        super(context, classLoader, prefs);
    }

    @NonNull
    @Override
    public String getName() {
        return "MessageDeviceSource";
    }

    @NonNull
    @Override
    public String getCategory() {
        return "Conversation";
    }

    @Override
    public void hook() {
        if (!isEnabled(PREF_KEY, false)) {
            return;
        }

        resolveMessageClasses();

        ActivityTracker.addListener(activity -> {
            String name = activity.getClass().getSimpleName();
            conversationActive = name.contains("Conversation");
        });

        hookPlaintextProcessor();
        hookListViewAdapter();
        hookTextViewSetText();
    }

    private void hookPlaintextProcessor() {
        try {
            Method targetMethod = DexSearchEngine.getInstance().findMethodWithCache(
                    context,
                    classLoader,
                    "waex_shared_msg_proc_plaintext",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create().matcher(
                                MethodMatcher.create().addUsingString("SharedMessageProcessor/handlePlaintext", StringMatchType.Contains)
                        )).firstOrNull();
                        return md != null ? md.getMethodInstance(loader) : null;
                    }
            );

            if (targetMethod != null) {
                XposedBridge.hookMethod(targetMethod, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (!isEnabled(PREF_KEY, false)) return;
                        Object message = findFMessage(param.args);
                        if (message == null) return;
                        String messageId = extractMessageId(message);
                        if (messageId != null && !messageId.isEmpty()) {
                            int devId = extractDeviceId(message);
                            if (devId >= 0) {
                                MessageDeviceSourceStore.getInstance(context).upsertDeviceId(messageId, devId);
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to hook plaintext processor: " + t.getMessage());
        }
    }

    private void hookListViewAdapter() {
        try {
            XposedHelpers.findAndHookMethod(
                    ListView.class,
                    "setAdapter",
                    ListAdapter.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            if (!isEnabled(PREF_KEY, false)) return;
                            Activity currentAct = ActivityTracker.getCurrentActivity();
                            if (currentAct == null) return;
                            String actName = currentAct.getClass().getSimpleName();
                            if (!actName.contains("Conversation")) return;

                            if (!(param.thisObject instanceof ListView)) return;

                            ListAdapter adapter = (ListAdapter) param.args[0];
                            if (adapter instanceof HeaderViewListAdapter) {
                                adapter = ((HeaderViewListAdapter) adapter).getWrappedAdapter();
                            }
                            if (adapter == null) return;

                            if (!hookedAdapterClasses.add(adapter.getClass())) return;

                            Method getViewMethod = findConcreteAdapterGetView(adapter.getClass());
                            if (getViewMethod == null) return;

                            XposedBridge.hookMethod(getViewMethod, new XC_MethodHook() {
                                @Override
                                protected void beforeHookedMethod(MethodHookParam p) {
                                    // The host may call setText() while populating convertView.
                                    // Remove stale annotation before that host work begins.
                                    if (p.args != null && p.args.length > 1
                                            && p.args[1] instanceof ViewGroup) {
                                        invalidateDeviceSourceRow((ViewGroup) p.args[1]);
                                    }
                                }

                                @Override
                                protected void afterHookedMethod(MethodHookParam p) {
                                    // A recycled convertView may not be returned by the adapter.
                                    // Invalidate both identities before any early exit, including
                                    // disabled settings, null items and adapter lookup failures.
                                    if (p.args != null && p.args.length > 1
                                            && p.args[1] instanceof ViewGroup
                                            && p.args[1] != p.getResult()) {
                                        invalidateDeviceSourceRow((ViewGroup) p.args[1]);
                                    }
                                    if (p.getResult() instanceof ViewGroup) {
                                        invalidateDeviceSourceRow((ViewGroup) p.getResult());
                                    }
                                    if (!isEnabled(PREF_KEY, false)) return;
                                    if (!(p.thisObject instanceof ListAdapter)) return;
                                    ListAdapter activeAdapter = (ListAdapter) p.thisObject;
                                    int pos = (int) p.args[0];
                                    if (!(p.getResult() instanceof ViewGroup)) return;
                                    ViewGroup row = (ViewGroup) p.getResult();

                                    Object item;
                                    try {
                                        // The method hook belongs to the adapter class and survives chat
                                        // recreation. Always read from the instance rendering this row;
                                        // capturing the first adapter leaves reopened chats bound to stale data.
                                        item = activeAdapter.getItem(pos);
                                    } catch (Throwable t) {
                                        return;
                                    }
                                    Object message = findFMessage(item);
                                    if (message == null) return;

                                    bindMessageRow(row, message);
                                }
                            });
                        }
                    }
            );
        } catch (Throwable t) {
            XposedBridge.log(TAG + " ListView setAdapter hook error: " + t.getMessage());
        }
    }

    private void resolveMessageClasses() {
        try {
            fMessageClass = DexSearchEngine.getInstance().findClassWithCache(
                    context,
                    classLoader,
                    "waex_fmessage_class",
                    (bridge, loader) -> {
                        MethodData data = bridge.findMethod(FindMethod.create().matcher(
                                MethodMatcher.create().addUsingString(
                                        "FMessage/getSenderUserJid/key.id",
                                        StringMatchType.Contains)
                        )).firstOrNull();
                        return data != null
                                ? data.getMethodInstance(loader).getDeclaringClass()
                                : null;
                    }
            );
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to resolve FMessage class: " + t.getMessage());
        }

        try {
            deviceJidClass = classLoader.loadClass("com.whatsapp.jid.DeviceJid");
        } catch (Throwable ignored) {
            try {
                deviceJidClass = DexSearchEngine.getInstance().findClassWithCache(
                        context,
                        classLoader,
                        "waex_device_jid_class",
                        (bridge, loader) -> {
                            var data = bridge.findClass(FindClass.create()
                                    .matcher(ClassMatcher.create()
                                            .className("jid.DeviceJid", StringMatchType.EndsWith)))
                                    .firstOrNull();
                            return data != null ? data.getInstance(loader) : null;
                        }
                );
            } catch (Throwable t) {
                XposedBridge.log(TAG + " Failed to resolve DeviceJid class: " + t.getMessage());
            }
        }
    }

    private Object findFMessage(Object[] candidates) {
        if (candidates == null) return null;
        for (Object candidate : candidates) {
            Object message = findFMessage(candidate);
            if (message != null) return message;
        }
        return null;
    }

    /** Resolves the typed FMessage from adapter items and plaintext-processor wrappers. */
    private Object findFMessage(Object candidate) {
        if (candidate == null || fMessageClass == null) return null;
        if (fMessageClass.isInstance(candidate)) return candidate;

        Class<?> current = candidate.getClass();
        while (current != null && current != Object.class) {
            for (Field field : current.getDeclaredFields()) {
                if (Modifier.isStatic(field.getModifiers())
                        || !fMessageClass.isAssignableFrom(field.getType())) {
                    continue;
                }
                try {
                    field.setAccessible(true);
                    Object nested = field.get(candidate);
                    if (nested != null) return nested;
                } catch (Throwable ignored) {
                }
            }
            current = current.getSuperclass();
        }
        return null;
    }

    @Nullable
    private static Method findConcreteAdapterGetView(@NonNull Class<?> adapterClass) {
        Class<?> current = adapterClass;
        while (current != null && current != Object.class) {
            try {
                Method method = current.getDeclaredMethod(
                        "getView", int.class, View.class, ViewGroup.class);
                if (!Modifier.isAbstract(method.getModifiers())) {
                    method.setAccessible(true);
                    return method;
                }
            } catch (NoSuchMethodException ignored) {
                // WhatsApp adapters commonly inherit this method from an obfuscated base.
            }
            current = current.getSuperclass();
        }
        return null;
    }

    private void bindMessageRow(ViewGroup row, Object messageObj) {
        TextView dateTextView = findDateTextView(row);
        if (dateTextView == null) return;

        String messageId = extractMessageId(messageObj);
        if (messageId == null || messageId.isEmpty()) return;

        DeviceSourceRowBinding binding = new DeviceSourceRowBinding();
        XposedHelpers.setAdditionalInstanceField(row, FIELD_DEVICE_ROW_BINDING, binding);
        binding.anchor = new WeakReference<>(dateTextView);
        trackDeviceSourceTarget(binding, dateTextView);
        XposedHelpers.setAdditionalInstanceField(dateTextView, FIELD_DEVICE_MSG_ID, messageId);
        dateTextView.setTag(R.id.wae_device_source_tag, Boolean.TRUE);

        CompletableFuture.supplyAsync(() -> resolveMessageDeviceId(messageId, messageObj))
                .thenAcceptAsync(resolvedDeviceId -> {
                    if (!binding.active || !isEnabled(PREF_KEY, false)
                            || XposedHelpers.getAdditionalInstanceField(row, FIELD_DEVICE_ROW_BINDING) != binding
                            || XposedHelpers.getAdditionalInstanceField(dateTextView, FIELD_DEVICE_ROW_BINDING) != binding
                            || findDateTextView(row) != dateTextView) return;
                    Object currentId = XposedHelpers.getAdditionalInstanceField(dateTextView, FIELD_DEVICE_MSG_ID);
                    if (!Objects.equals(currentId, messageId)) return;

                    String suffix = getDeviceEmojiSuffix(resolvedDeviceId);
                    XposedHelpers.setAdditionalInstanceField(dateTextView, FIELD_DEVICE_SUFFIX, suffix);

                    bindDeviceSourceUi(dateTextView, resolvedDeviceId, binding);
                    if (!suffix.isEmpty()) {
                        applyDeviceSourceToMatchingViews(row, dateTextView, suffix, resolvedDeviceId, binding);
                    }
                }, UI_EXECUTOR);
    }

    private void trackDeviceSourceTarget(DeviceSourceRowBinding binding, TextView target) {
        binding.targets.add(new WeakReference<>(target));
        XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_ROW_BINDING, binding);
    }

    private void invalidateDeviceSourceRow(ViewGroup row) {
        Object previous = XposedHelpers.removeAdditionalInstanceField(row, FIELD_DEVICE_ROW_BINDING);
        if (!(previous instanceof DeviceSourceRowBinding)) return;
        DeviceSourceRowBinding binding = (DeviceSourceRowBinding) previous;
        // Make captured click listeners and delayed completions inert first.
        binding.active = false;
        for (WeakReference<TextView> tracked : binding.targets) {
            TextView target = tracked.get();
            if (target == null) continue;
            if (XposedHelpers.getAdditionalInstanceField(target, FIELD_DEVICE_ROW_BINDING) != binding) continue;
            clearDeviceSourceTarget(target);
        }
        binding.targets.clear();
    }

    /** Restore only the suffix that was actually produced by this hook. */
    private String unannotatedText(TextView target) {
        String current = String.valueOf(target.getText());
        Object rendered = XposedHelpers.getAdditionalInstanceField(target, FIELD_DEVICE_RENDERED_TEXT);
        Object original = XposedHelpers.getAdditionalInstanceField(target, FIELD_DEVICE_ORIGINAL_TEXT);
        return current.equals(rendered) && original instanceof String ? (String) original : current;
    }

    private void renderDeviceSourceText(TextView target, String original, String suffix) {
        String desired = original + suffix;
        XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_GUARD, true);
        try {
            if (!desired.equals(String.valueOf(target.getText()))) target.setText(desired);
            // Immutable strings only: never keep a View or mutable Spannable
            // reachable from Xposed's global weak-key additional-field table.
            XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_ORIGINAL_TEXT, original);
            XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_RENDERED_TEXT,
                    String.valueOf(target.getText()));
        } finally {
            XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_GUARD, false);
        }
    }

    private void clearDeviceSourceTarget(TextView target) {
        String current = String.valueOf(target.getText());
        String original = unannotatedText(target);
        XposedHelpers.removeAdditionalInstanceField(target, FIELD_DEVICE_ROW_BINDING);
        attachClickToast(target, -1, null);
        XposedHelpers.removeAdditionalInstanceField(target, FIELD_DEVICE_SUFFIX);
        XposedHelpers.removeAdditionalInstanceField(target, FIELD_DEVICE_MSG_ID);
        XposedHelpers.removeAdditionalInstanceField(target, FIELD_DEVICE_ORIGINAL_TEXT);
        XposedHelpers.removeAdditionalInstanceField(target, FIELD_DEVICE_RENDERED_TEXT);
        target.setTag(R.id.wae_device_source_tag, null);
        if (!current.equals(original)) {
            XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_GUARD, true);
            try {
                target.setText(original);
            } finally {
                XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_GUARD, false);
            }
        }
    }

    private static volatile int sDateResId = -1;
    private static volatile int sDateWrapperResId = -1;

    private TextView findDateTextView(ViewGroup row) {
        if (sDateResId == -1) {
            Context ctx = row.getContext();
            sDateResId = ctx.getResources().getIdentifier("date", "id", ctx.getPackageName());
            sDateWrapperResId = ctx.getResources().getIdentifier("date_wrapper", "id", ctx.getPackageName());
        }

        if (sDateResId > 0) {
            View target = row.findViewById(sDateResId);
            if (target instanceof TextView) return (TextView) target;
        }

        if (sDateWrapperResId > 0) {
            View wrapper = row.findViewById(sDateWrapperResId);
            if (wrapper instanceof ViewGroup) {
                ViewGroup wg = (ViewGroup) wrapper;
                for (int i = 0; i < wg.getChildCount(); i++) {
                    View child = wg.getChildAt(i);
                    if (child instanceof TextView) return (TextView) child;
                }
            }
        }

        // Slow fallback only if resource IDs were not found by name
        if (sDateResId == 0 && sDateWrapperResId == 0) {
            View target = findChildByResourceName(row, "date");
            if (target instanceof TextView) return (TextView) target;

            View wrapper = findChildByResourceName(row, "date_wrapper");
            if (wrapper instanceof ViewGroup) {
                ViewGroup wg = (ViewGroup) wrapper;
                for (int i = 0; i < wg.getChildCount(); i++) {
                    View child = wg.getChildAt(i);
                    if (child instanceof TextView) return (TextView) child;
                }
            }
        }
        return null;
    }

    private View findChildByResourceName(ViewGroup viewGroup, String targetResName) {
        for (int i = 0; i < viewGroup.getChildCount(); i++) {
            View child = viewGroup.getChildAt(i);
            if (targetResName.equals(getResourceEntryName(child))) return child;
            if (child instanceof ViewGroup) {
                View found = findChildByResourceName((ViewGroup) child, targetResName);
                if (found != null) return found;
            }
        }
        return null;
    }

    private String getResourceEntryName(View view) {
        int id = view.getId();
        if (id == View.NO_ID) return null;
        try {
            return view.getResources().getResourceEntryName(id);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private int resolveMessageDeviceId(String messageId, Object messageObj) {
        int liveId = extractDeviceId(messageObj);
        if (liveId >= 0) {
            MessageDeviceSourceStore.getInstance(context).upsertDeviceId(messageId, liveId);
            return liveId;
        }
        return MessageDeviceSourceStore.getInstance(context).getDeviceId(messageId);
    }

    private String getDeviceEmojiSuffix(int deviceId) {
        if (deviceId == 0) return PRIMARY_DEVICE_EMOJI;
        if (deviceId > 0) return LINKED_DEVICE_EMOJI;
        return "";
    }

    private void bindDeviceSourceUi(TextView dateTextView, int deviceId) {
        bindDeviceSourceUi(dateTextView, deviceId, null);
    }

    private void bindDeviceSourceUi(TextView dateTextView, int deviceId, DeviceSourceRowBinding binding) {
        String baseText = unannotatedText(dateTextView);
        String suffix = getDeviceEmojiSuffix(deviceId);
        XposedHelpers.setAdditionalInstanceField(dateTextView, FIELD_DEVICE_SUFFIX, suffix);

        attachClickToast(dateTextView, deviceId, binding);
        renderDeviceSourceText(dateTextView, baseText, suffix);
    }

    private void applyDeviceSourceToMatchingViews(ViewGroup root, TextView anchor, String suffix, int deviceId,
                                                   DeviceSourceRowBinding binding) {
        String anchorBase = unannotatedText(anchor);
        if (TextUtils.isEmpty(anchorBase)) return;

        forEachTextView(root, textView -> {
            if (textView == anchor) return;
            String base = unannotatedText(textView);
            if (!anchorBase.equals(base)) return;

            trackDeviceSourceTarget(binding, textView);
            textView.setTag(R.id.wae_device_source_tag, Boolean.TRUE);
            XposedHelpers.setAdditionalInstanceField(textView, FIELD_DEVICE_SUFFIX, suffix);
            attachClickToast(textView, deviceId, binding);
            renderDeviceSourceText(textView, base, suffix);
        });
    }

    private void attachClickToast(TextView textView, int deviceId) {
        attachClickToast(textView, deviceId, null);
    }

    private void attachClickToast(TextView textView, int deviceId, DeviceSourceRowBinding binding) {
        Object tracked = XposedHelpers.getAdditionalInstanceField(textView, FIELD_DEVICE_CLICK_LISTENER);
        DeviceSourceClickListener owned = tracked instanceof DeviceSourceClickListener
                ? (DeviceSourceClickListener) tracked : null;
        if (owned != null) owned.deviceId = -1;

        final View.OnClickListener current;
        try {
            current = readDeviceSourceClickListener(textView);
        } catch (ReflectiveOperationException | RuntimeException unavailable) {
            // An unreadable listener slot is not permission to overwrite its owner.
            return;
        }

        if (owned != null && current != owned) {
            XposedHelpers.removeAdditionalInstanceField(textView, FIELD_DEVICE_CLICK_LISTENER);
            owned = null;
        }

        if (deviceId < 0 || XposedHelpers.getAdditionalInstanceField(textView, "waex_stt_file") != null) {
            if (owned != null) {
                boolean keepClickable = owned.wasClickable && textView.isClickable();
                textView.setOnClickListener(null);
                textView.setClickable(keepClickable);
                XposedHelpers.removeAdditionalInstanceField(textView, FIELD_DEVICE_CLICK_LISTENER);
            }
            return;
        }

        // Preserve existing host/feature actions, including replacements of an
        // earlier WAEX callback. A rebound message gets a new callback identity.
        if (current != null && owned == null) return;
        boolean wasClickable = owned != null ? owned.wasClickable : textView.isClickable();
        DeviceSourceClickListener listener = new DeviceSourceClickListener(deviceId, wasClickable, binding);
        XposedHelpers.setAdditionalInstanceField(textView, FIELD_DEVICE_CLICK_LISTENER, listener);
        textView.setOnClickListener(listener);
    }

    private static View.OnClickListener readDeviceSourceClickListener(View view)
            throws ReflectiveOperationException {
        Field infoField = sDeviceListenerInfoField;
        if (infoField == null) {
            infoField = View.class.getDeclaredField("mListenerInfo");
            infoField.setAccessible(true);
            sDeviceListenerInfoField = infoField;
        }
        Object info = infoField.get(view);
        if (info == null) return null;

        Field clickField = sDeviceOnClickListenerField;
        if (clickField == null) {
            clickField = info.getClass().getDeclaredField("mOnClickListener");
            clickField.setAccessible(true);
            sDeviceOnClickListenerField = clickField;
        }
        return (View.OnClickListener) clickField.get(info);
    }

    private final class DeviceSourceClickListener implements View.OnClickListener {
        private int deviceId;
        private final boolean wasClickable;
        private final DeviceSourceRowBinding binding;

        DeviceSourceClickListener(int deviceId, boolean wasClickable, DeviceSourceRowBinding binding) {
            this.deviceId = deviceId;
            this.wasClickable = wasClickable;
            this.binding = binding;
        }

        @Override
        public void onClick(View view) {
            int currentDeviceId = deviceId;
            if (currentDeviceId < 0 || !isEnabled(PREF_KEY, false)
                    || (binding != null && (!binding.active
                            || XposedHelpers.getAdditionalInstanceField(view, FIELD_DEVICE_ROW_BINDING) != binding))
                    || XposedHelpers.getAdditionalInstanceField(view, FIELD_DEVICE_CLICK_LISTENER) != this
                    || XposedHelpers.getAdditionalInstanceField(view, "waex_stt_file") != null) return;
            try {
                if (readDeviceSourceClickListener(view) != this) return;
            } catch (ReflectiveOperationException | RuntimeException unavailable) {
                return;
            }
            Context ctx = view.getContext();
            if (currentDeviceId == 0) {
                Toast.makeText(ctx, UiText.get(R.string.message_sent_via_phone, "This message was sent via Phone"), Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(ctx, UiText.get(R.string.waex_ui_this_message_was_sent_via_a_linked_dev, "This message was sent via a Linked Device (Desktop/Phone)"), Toast.LENGTH_SHORT).show();
            }
        }
    }

    private void forEachTextView(View view, Consumer<TextView> consumer) {
        if (view instanceof TextView) {
            consumer.accept((TextView) view);
            return;
        }
        if (!(view instanceof ViewGroup)) return;
        ViewGroup group = (ViewGroup) view;
        for (int i = 0; i < group.getChildCount(); i++) {
            forEachTextView(group.getChildAt(i), consumer);
        }
    }

    private void hookTextViewSetText() {
        XC_MethodHook setTextHook = new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (!conversationActive || !isEnabled(PREF_KEY, false)) return;
                if (!(param.thisObject instanceof TextView)) return;
                TextView textView = (TextView) param.thisObject;

                Object tag = textView.getTag(R.id.wae_device_source_tag);
                if (tag == null) return;

                Object suffixObj = XposedHelpers.getAdditionalInstanceField(textView, FIELD_DEVICE_SUFFIX);
                if (!(suffixObj instanceof String) || ((String) suffixObj).isEmpty()) return;
                String suffix = (String) suffixObj;

                if (Boolean.TRUE.equals(XposedHelpers.getAdditionalInstanceField(textView, FIELD_DEVICE_GUARD))) return;

                Object state = XposedHelpers.getAdditionalInstanceField(textView, FIELD_DEVICE_ROW_BINDING);
                if (state instanceof DeviceSourceRowBinding) {
                    DeviceSourceRowBinding binding = (DeviceSourceRowBinding) state;
                    // A host update to a secondary text view ends our ownership
                    // of that annotation until a fresh adapter bind establishes
                    // whether this view still describes the same message.
                    if (!binding.active || binding.anchor == null
                            || binding.anchor.get() != textView) {
                        clearDeviceSourceTarget(textView);
                        return;
                    }
                }

                String current = String.valueOf(textView.getText());
                String base = unannotatedText(textView);
                String desired = base + suffix;
                if (desired.equals(current)) return;

                renderDeviceSourceText(textView, base, suffix);
            }
        };

        try {
            Method internalSetText = null;
            for (Method m : TextView.class.getDeclaredMethods()) {
                if (!m.getName().equals("setText")) continue;
                Class<?>[] methodParameters = m.getParameterTypes();
                if (methodParameters.length == 4
                        && methodParameters[0] == CharSequence.class
                        && methodParameters[1] == TextView.BufferType.class
                        && methodParameters[2] == boolean.class
                        && methodParameters[3] == int.class) {
                    internalSetText = m;
                    break;
                }
            }
            if (internalSetText != null) {
                XposedBridge.hookMethod(internalSetText, setTextHook);
                return;
            }
        } catch (Throwable ignored) {}

        XposedBridge.hookAllMethods(TextView.class, "setText", setTextHook);
    }

    private String extractMessageId(Object messageObj) {
        if (messageObj == null) return null;
        try {
            Class<?> curr = messageObj.getClass();
            while (curr != null && curr != Object.class) {
                for (Field field : curr.getDeclaredFields()) {
                    field.setAccessible(true);
                    Object val = field.get(messageObj);
                    if (val == null) continue;
                    String className = val.getClass().getName();
                    if (className.contains("Key") || val.toString().startsWith("Key(")) {
                        String id = extractIdFromKeyObj(val);
                        if (id != null && !id.isEmpty()) return id;
                    }
                }
                curr = curr.getSuperclass();
            }

            Pattern pattern = Pattern.compile("(?:messageId|messageID|keyId|Key\\(id)=([A-Za-z0-9_-]+)");
            var matcher = pattern.matcher(messageObj.toString());
            if (matcher.find()) return matcher.group(1);
        } catch (Throwable ignored) {}
        return null;
    }

    private String extractIdFromKeyObj(Object keyObj) {
        try {
            Class<?> curr = keyObj.getClass();
            while (curr != null && curr != Object.class) {
                for (Field f : curr.getDeclaredFields()) {
                    f.setAccessible(true);
                    if (f.getType() == String.class) {
                        // Message-key member names are obfuscated (often A00/A01). The key has a
                        // single String payload, so validate its value instead of its field name.
                        String value = (String) f.get(keyObj);
                        if (value != null && value.length() >= 8 && !value.contains("@")
                                && value.indexOf(' ') < 0) return value;
                    }
                }
                curr = curr.getSuperclass();
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private int extractDeviceId(Object messageObj) {
        if (messageObj == null) return -1;
        try {
            Object deviceJid = getDeviceJidObject(messageObj);
            if (deviceJid != null) {
                try {
                    return (Integer) XposedHelpers.callMethod(deviceJid, "getDevice");
                } catch (Throwable ignored) {}

                try {
                    String raw = (String) XposedHelpers.callMethod(deviceJid, "getRawString");
                    int dev = parseDeviceIdFromRawString(raw);
                    if (dev >= 0) return dev;
                } catch (Throwable ignored) {}
            }

            // Fallback: check raw string representation on message object fields
            Class<?> curr = messageObj.getClass();
            while (curr != null && curr != Object.class) {
                for (Field f : curr.getDeclaredFields()) {
                    if (Modifier.isStatic(f.getModifiers())) continue;
                    f.setAccessible(true);
                    Object val = f.get(messageObj);
                    if (val == null) continue;
                    String name = val.getClass().getName();
                    if (name.contains("Jid") || name.contains("jid")) {
                        try {
                            String raw = (String) XposedHelpers.callMethod(val, "getRawString");
                            int dev = parseDeviceIdFromRawString(raw);
                            if (dev >= 0) return dev;
                        } catch (Throwable ignored) {}
                    }
                }
                curr = curr.getSuperclass();
            }
        } catch (Throwable ignored) {}
        return -1;
    }

    private Object getDeviceJidObject(Object messageObj) {
        try {
            if (deviceJidClass == null) {
                resolveMessageClasses();
            }

            if (deviceJidClass != null) {
                Class<?> curr = messageObj.getClass();
                while (curr != null && curr != Object.class) {
                    for (Field f : curr.getDeclaredFields()) {
                        if (deviceJidClass.isAssignableFrom(f.getType())) {
                            f.setAccessible(true);
                            Object dj = f.get(messageObj);
                            if (dj != null) return dj;
                        }
                    }
                    curr = curr.getSuperclass();
                }
            }
        } catch (Throwable ignored) {}
        return null;
    }

    private static int parseDeviceIdFromRawString(String raw) {
        if (raw == null) return -1;
        try {
            int dotIdx = raw.indexOf('.');
            int atIdx = raw.indexOf('@');
            if (dotIdx != -1 && atIdx != -1 && dotIdx < atIdx) {
                String devPart = raw.substring(dotIdx + 1, atIdx);
                int colonIdx = devPart.indexOf(':');
                if (colonIdx != -1) {
                    devPart = devPart.substring(0, colonIdx);
                }
                return Integer.parseInt(devPart);
            }
        } catch (Throwable ignored) {}
        return -1;
    }
}
