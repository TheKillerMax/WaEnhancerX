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

    private final List<FeatureEntry> features = new ArrayList<>();

    public static final class FeatureEntry {
        public final BaseFeature feature;
        public final String name;
        public final String className;
        public final String category;
        public String status = "INITIALIZED";
        public String error = null;

        public FeatureEntry(BaseFeature feature, String category) {
            this.feature = feature;
            this.name = feature.getName();
            this.className = feature.getClass().getSimpleName();
            this.category = category;
        }

        public FeatureEntry(String name, String className, String category, String status) {
            this.feature = null;
            this.name = name;
            this.className = className;
            this.category = category;
            this.status = status;
        }
    }

    public FeatureRegistry(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs) {
        // Initialize Native WhatsApp WDS / Material Dialog engine
        NativeWhatsAppDialog.Companion.initialize(context, classLoader);
        try {
            BootloaderSpooferFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Bootloader Spoofing & Integrity", "BootloaderSpooferFeature", "Licensing", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Bootloader Spoofing & Integrity", "BootloaderSpooferFeature", "Licensing", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }

        // Privacy & Seen Controls
        addFeature(new AntiViewOnceHook(context, classLoader, prefs), "Privacy");
        addFeature(new TypingPrivacyHook(context, classLoader, prefs), "Privacy");
        addFeature(new FreezeLastSeenHook(context, classLoader, prefs), "Privacy");
        addFeature(new AlwaysOnlineHook(context, classLoader, prefs), "Privacy");
        addFeature(new HideReceiptsHook(context, classLoader, prefs), "Privacy");
        addFeature(new BlueOnReplyHook(context, classLoader, prefs), "Privacy");
        addFeature(new CallPrivacyHook(context, classLoader, prefs), "Privacy");
        addFeature(new AntiRevokeHook(context, classLoader, prefs), "Privacy");
        addFeature(new HideForwardedTagHook(context, classLoader, prefs), "Privacy");
        addFeature(new CustomPrivacyHook(context, classLoader, prefs), "Privacy");
        addFeature(new AutoNextStatusHook(context, classLoader, prefs), "Privacy");
        addFeature(new AntiDisappearingMessagesHook(context, classLoader, prefs), "Privacy");
        addFeature(new LockedChatsEnhancerHook(context, classLoader, prefs), "Privacy");
        addFeature(new HideArchivedChatsHook(context, classLoader, prefs), "Privacy");
        addFeature(new DndModeHook(context, classLoader, prefs), "Privacy");
        addFeature(new HideChatsVaultHook(context, classLoader, prefs), "Privacy");

        // Conversation & Message Controls
        addFeature(new AntiEditMessagesHook(context, classLoader, prefs), "Conversation");
        addFeature(new StickerConfirmHook(context, classLoader, prefs), "Conversation");
        addFeature(new JumpFirstMessageHook(context, classLoader, prefs), "Conversation");
        addFeature(new PreserveDeleteForMeHook(context, classLoader, prefs), "Conversation");
        addFeature(new CopyStatusTextHook(context, classLoader, prefs), "Conversation");
        addFeature(new ChatLimitsBypassHook(context, classLoader, prefs), "Conversation");
        addFeature(new DoubleTapReactionHook(context, classLoader, prefs), "Conversation");
        addFeature(new MinorFixesHook(context, classLoader, prefs), "Conversation");
        try {
            MessageBomberFeature.install(context, classLoader, prefs);
            features.add(new FeatureEntry("Message Bomber", "MessageBomberFeature", "Conversation", "ACTIVE"));
        } catch (Throwable t) {
            FeatureEntry entry = new FeatureEntry("Message Bomber", "MessageBomberFeature", "Conversation", "FAILED");
            entry.error = t.getMessage();
            features.add(entry);
        }

        // Homescreen & Layout Controls
        addFeature(new HomeScreenHeaderActionsHook(context, classLoader, prefs), "Customization");
        addFeature(new ChatListCustomizationsHook(context, classLoader, prefs), "Customization");

        // Media & Audio Controls
        addFeature(new DownloadViewOnceHook(context, classLoader, prefs), "Media");
        addFeature(new StatusDownloadHook(context, classLoader, prefs), "Media");
        addFeature(new MediaQualityBypassHook(context, classLoader, prefs), "Media");
        addFeature(new MediaPreviewHook(context, classLoader, prefs), "Media");
        addFeature(new ProximitySensorHook(context, classLoader, prefs), "Media");
        addFeature(new CallRecordingHook(context, classLoader, prefs), "Media");
        addFeature(new ProfilePhotoDownloadHook(context, classLoader, prefs), "Media");
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
        addFeature(new PresenceToastsHook(context, classLoader, prefs), "Automation");
        addFeature(new TaskerIntegrationHook(context, classLoader, prefs), "Automation");
        addFeature(new ChatBubbleColorsHook(context, classLoader, prefs), "Customization");
        addFeature(new ChannelRecommendationsFilterHook(context, classLoader, prefs), "Customization");
        addFeature(new OnlinePresenceIndicatorsHook(context, classLoader, prefs), "Customization");
        addFeature(new SeparateGroupsHook(context, classLoader, prefs), "Customization");
        addFeature(new FloatingBottomBarHook(context, classLoader, prefs), "Customization");
        addFeature(new FilterItemsHook(context, classLoader, prefs), "Customization");
    }

    private void addFeature(BaseFeature feature, String category) {
        features.add(new FeatureEntry(feature, category));
    }

    public void initializeAll() {
        for (FeatureEntry entry : features) {
            if (entry.feature != null) {
                try {
                    entry.feature.hook();
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
            XposedBridge.log("[WAEX] Successfully reported " + features.size() + " injected hooks for " + packageName);
        } catch (Throwable t) {
            XposedBridge.log("[WAEX] Failed to report injected hooks: " + t.getMessage());
        }
    }
}
