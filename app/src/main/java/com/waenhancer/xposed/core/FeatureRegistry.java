package com.waenhancer.xposed.core;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.components.NativeWhatsAppDialog;
import com.waenhancer.xposed.features.automation.PresenceToastsHook;
import com.waenhancer.xposed.features.automation.TaskerIntegrationHook;
import com.waenhancer.xposed.features.conversation.AntiEditMessagesHook;
import com.waenhancer.xposed.features.conversation.ChatBubbleColorsHook;
import com.waenhancer.xposed.features.conversation.ChatLimitsBypassHook;
import com.waenhancer.xposed.features.conversation.CopyStatusTextHook;
import com.waenhancer.xposed.features.conversation.DoubleTapReactionHook;
import com.waenhancer.xposed.features.conversation.JumpFirstMessageHook;
import com.waenhancer.xposed.features.conversation.MinorFixesHook;
import com.waenhancer.xposed.features.conversation.PreserveDeleteForMeHook;
import com.waenhancer.xposed.features.conversation.StickerConfirmHook;
import com.waenhancer.xposed.features.customization.ChannelRecommendationsFilterHook;
import com.waenhancer.xposed.features.customization.FilterItemsHook;
import com.waenhancer.xposed.features.customization.FloatingBottomBarHook;
import com.waenhancer.xposed.features.customization.OnlinePresenceIndicatorsHook;
import com.waenhancer.xposed.features.customization.SeparateGroupsHook;
import com.waenhancer.xposed.features.homescreen.ChatListCustomizationsHook;
import com.waenhancer.xposed.features.homescreen.HomeScreenHeaderActionsHook;
import com.waenhancer.xposed.features.media.CallRecordingHook;
import com.waenhancer.xposed.features.media.DownloadViewOnceHook;
import com.waenhancer.xposed.features.media.MediaPreviewHook;
import com.waenhancer.xposed.features.media.MediaQualityBypassHook;
import com.waenhancer.xposed.features.media.ProfilePhotoDownloadHook;
import com.waenhancer.xposed.features.media.ProximitySensorHook;
import com.waenhancer.xposed.features.media.StatusDownloadHook;
import com.waenhancer.xposed.features.privacy.AlwaysOnlineHook;
import com.waenhancer.xposed.features.privacy.AntiDisappearingMessagesHook;
import com.waenhancer.xposed.features.privacy.AntiRevokeHook;
import com.waenhancer.xposed.features.privacy.AntiViewOnceHook;
import com.waenhancer.xposed.features.privacy.AutoNextStatusHook;
import com.waenhancer.xposed.features.privacy.BlueOnReplyHook;
import com.waenhancer.xposed.features.privacy.CallPrivacyHook;
import com.waenhancer.xposed.features.privacy.CustomPrivacyHook;
import com.waenhancer.xposed.features.privacy.DndModeHook;
import com.waenhancer.xposed.features.privacy.FreezeLastSeenHook;
import com.waenhancer.xposed.features.privacy.HideArchivedChatsHook;
import com.waenhancer.xposed.features.privacy.HideChatsVaultHook;
import com.waenhancer.xposed.features.privacy.HideForwardedTagHook;
import com.waenhancer.xposed.features.privacy.HideReceiptsHook;
import com.waenhancer.xposed.features.privacy.LockedChatsEnhancerHook;
import com.waenhancer.xposed.features.privacy.TypingPrivacyHook;
import com.waenhancer.licensing.features.AudioToVoiceStatusFeature;
import com.waenhancer.licensing.features.BootloaderSpooferFeature;
import com.waenhancer.licensing.features.FileSizeSpooferFeature;
import com.waenhancer.licensing.features.MessageBomberFeature;
import com.waenhancer.licensing.features.NewChatFeature;
import com.waenhancer.licensing.features.StatusSplitterFeature;
import de.robv.android.xposed.XposedBridge;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

/**
 * Orchestrates and registers all modular hooks in WAEX and reports injected status.
 */
public final class FeatureRegistry {

    @FunctionalInterface
    private interface FeatureFactory {
        BaseFeature create() throws Throwable;
    }

    private final List<FeatureEntry> features = new ArrayList<>();

    public static final class FeatureEntry {
        public BaseFeature feature;
        private final FeatureFactory factory;
        public String name;
        public String className;
        public final String category;
        public String status = "INITIALIZED";
        public String error = null;

        public FeatureEntry(BaseFeature feature, String category) {
            this.feature = feature;
            this.factory = null;
            this.name = feature.getName();
            this.className = feature.getClass().getSimpleName();
            this.category = category;
        }

        FeatureEntry(FeatureFactory factory, String className, String category) {
            this.feature = null;
            this.factory = factory;
            this.name = className;
            this.className = className;
            this.category = category;
        }

        public FeatureEntry(String name, String className, String category, String status) {
            this.feature = null;
            this.factory = null;
            this.name = name;
            this.className = className;
            this.category = category;
            this.status = status;
        }
    }

    public FeatureRegistry(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        // Initialize Native WhatsApp WDS / Material Dialog engine
        try {
            NativeWhatsAppDialog.Companion.initialize(context, classLoader);
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Native WhatsApp Dialog",
                    "NativeWhatsAppDialog", "Core", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
            XposedBridge.log("[WAEX] Native dialog initialization failed: " + t);
        }
        try {
            BootloaderSpooferFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Bootloader Spoofing & Integrity", "BootloaderSpooferFeature", "Licensing", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Bootloader Spoofing & Integrity", "BootloaderSpooferFeature", "Licensing", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }

        // Privacy & Seen Controls
        addFeature(() -> new AntiViewOnceHook(context, classLoader, prefs), "AntiViewOnceHook", "Privacy");
        addFeature(() -> new TypingPrivacyHook(context, classLoader, prefs), "TypingPrivacyHook", "Privacy");
        addFeature(() -> new FreezeLastSeenHook(context, classLoader, prefs), "FreezeLastSeenHook", "Privacy");
        addFeature(() -> new AlwaysOnlineHook(context, classLoader, prefs), "AlwaysOnlineHook", "Privacy");
        addFeature(() -> new HideReceiptsHook(context, classLoader, prefs), "HideReceiptsHook", "Privacy");
        addFeature(() -> new BlueOnReplyHook(context, classLoader, prefs), "BlueOnReplyHook", "Privacy");
        addFeature(() -> new CallPrivacyHook(context, classLoader, prefs), "CallPrivacyHook", "Privacy");
        addFeature(() -> new AntiRevokeHook(context, classLoader, prefs), "AntiRevokeHook", "Privacy");
        addFeature(() -> new HideForwardedTagHook(context, classLoader, prefs), "HideForwardedTagHook", "Privacy");
        addFeature(() -> new CustomPrivacyHook(context, classLoader, prefs), "CustomPrivacyHook", "Privacy");
        addFeature(() -> new AutoNextStatusHook(context, classLoader, prefs), "AutoNextStatusHook", "Privacy");
        addFeature(() -> new AntiDisappearingMessagesHook(context, classLoader, prefs), "AntiDisappearingMessagesHook", "Privacy");
        addFeature(() -> new LockedChatsEnhancerHook(context, classLoader, prefs), "LockedChatsEnhancerHook", "Privacy");
        addFeature(() -> new HideArchivedChatsHook(context, classLoader, prefs), "HideArchivedChatsHook", "Privacy");
        addFeature(() -> new DndModeHook(context, classLoader, prefs), "DndModeHook", "Privacy");
        addFeature(() -> new HideChatsVaultHook(context, classLoader, prefs), "HideChatsVaultHook", "Privacy");

        // Conversation & Message Controls
        addFeature(() -> new AntiEditMessagesHook(context, classLoader, prefs), "AntiEditMessagesHook", "Conversation");
        addFeature(() -> new StickerConfirmHook(context, classLoader, prefs), "StickerConfirmHook", "Conversation");
        addFeature(() -> new JumpFirstMessageHook(context, classLoader, prefs), "JumpFirstMessageHook", "Conversation");
        addFeature(() -> new PreserveDeleteForMeHook(context, classLoader, prefs), "PreserveDeleteForMeHook", "Conversation");
        addFeature(() -> new CopyStatusTextHook(context, classLoader, prefs), "CopyStatusTextHook", "Conversation");
        addFeature(() -> new ChatLimitsBypassHook(context, classLoader, prefs), "ChatLimitsBypassHook", "Conversation");
        addFeature(() -> new DoubleTapReactionHook(context, classLoader, prefs), "DoubleTapReactionHook", "Conversation");
        addFeature(() -> new MinorFixesHook(context, classLoader, prefs), "MinorFixesHook", "Conversation");
        try {
            boolean installed = NewChatFeature.install(classLoader, prefs);
            features.add(new FeatureEntry("New Chat", "NewChatFeature", "Conversation",
                    installed ? "ACTIVE" : "DISABLED"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("New Chat", "NewChatFeature", "Conversation", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }
        try {
            MessageBomberFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Message Bomber", "MessageBomberFeature", "Conversation", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Message Bomber", "MessageBomberFeature", "Conversation", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }

        // Homescreen & Layout Controls
        addFeature(() -> new HomeScreenHeaderActionsHook(context, classLoader, prefs), "HomeScreenHeaderActionsHook", "Customization");
        addFeature(() -> new ChatListCustomizationsHook(context, classLoader, prefs), "ChatListCustomizationsHook", "Customization");

        // Media & Audio Controls
        addFeature(() -> new DownloadViewOnceHook(context, classLoader, prefs), "DownloadViewOnceHook", "Media");
        addFeature(() -> new StatusDownloadHook(context, classLoader, prefs), "StatusDownloadHook", "Media");
        addFeature(() -> new MediaQualityBypassHook(context, classLoader, prefs), "MediaQualityBypassHook", "Media");
        addFeature(() -> new MediaPreviewHook(context, classLoader, prefs), "MediaPreviewHook", "Media");
        addFeature(() -> new ProximitySensorHook(context, classLoader, prefs), "ProximitySensorHook", "Media");
        addFeature(() -> new CallRecordingHook(context, classLoader, prefs), "CallRecordingHook", "Media");
        addFeature(() -> new ProfilePhotoDownloadHook(context, classLoader, prefs), "ProfilePhotoDownloadHook", "Media");
        try {
            AudioToVoiceStatusFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Audio to Voice Status", "AudioToVoiceStatusFeature", "Media", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Audio to Voice Status", "AudioToVoiceStatusFeature", "Media", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }
        try {
            StatusSplitterFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Status Splitter", "StatusSplitterFeature", "Media", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Status Splitter", "StatusSplitterFeature", "Media", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }
        try {
            FileSizeSpooferFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("File Size Spoofer", "FileSizeSpooferFeature", "Media", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("File Size Spoofer", "FileSizeSpooferFeature", "Media", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }

        // Automation & Notification Controls
        addFeature(() -> new PresenceToastsHook(context, classLoader, prefs), "PresenceToastsHook", "Automation");
        addFeature(() -> new TaskerIntegrationHook(context, classLoader, prefs), "TaskerIntegrationHook", "Automation");
        addFeature(() -> new ChatBubbleColorsHook(context, classLoader, prefs), "ChatBubbleColorsHook", "Customization");
        addFeature(() -> new ChannelRecommendationsFilterHook(context, classLoader, prefs), "ChannelRecommendationsFilterHook", "Customization");
        addFeature(() -> new OnlinePresenceIndicatorsHook(context, classLoader, prefs), "OnlinePresenceIndicatorsHook", "Customization");
        addFeature(() -> new SeparateGroupsHook(context, classLoader, prefs), "SeparateGroupsHook", "Customization");
        addFeature(() -> new FloatingBottomBarHook(context, classLoader, prefs), "FloatingBottomBarHook", "Customization");
        addFeature(() -> new FilterItemsHook(context, classLoader, prefs), "FilterItemsHook", "Customization");
    }

    private void addFeature(FeatureFactory factory, String className, String category) {
        features.add(new FeatureEntry(factory, className, category));
    }

    public void initializeAll() {
        for (FeatureEntry entry : features) {
            if (entry.factory != null) {
                try {
                    BaseFeature feature = entry.factory.create();
                    entry.feature = feature;
                    entry.name = feature.getName();
                    entry.className = feature.getClass().getSimpleName();
                    feature.hook();
                    entry.status = "ACTIVE";
                } catch (Throwable t) {
                    entry.status = "FAILED";
                    entry.error = t.getMessage();
                    XposedBridge.log("[WAEX] Error initializing feature [" + entry.name + "]: " + t.getMessage());
                }
            }
        }
    }

    public void reportInjectedHooks(@NonNull Context context, @NonNull String packageName) {
        try {
            JSONArray array = new JSONArray();
            for (FeatureEntry entry : features) {
                JSONObject obj = new JSONObject();
                obj.put("name", entry.name);
                obj.put("className", entry.className);
                obj.put("category", entry.category);
                obj.put("status", entry.status);
                if (entry.error != null) {
                    obj.put("error", entry.error);
                }
                array.put(obj);
            }

            Uri uri = Uri.parse("content://com.waenhancer.hookprovider");
            Bundle extras = new Bundle();
            extras.putString("package", packageName);
            extras.putString("hooks_json", array.toString());
            extras.putLong("timestamp", System.currentTimeMillis());

            context.getContentResolver().call(uri, "register_injected_hooks", packageName, extras);
        } catch (Throwable t) {
            XposedBridge.log("[WAEX] Failed to report injected hooks: " + t.getMessage());
        }
    }
}
