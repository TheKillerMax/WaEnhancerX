package com.waenhancer.config

import java.util.Collections

/**
 * Unified catalog of features and user preferences across WA Enhancer.
 *
 * Serves as the single source of truth for:
 * 1. Feature search indexing in the Manager UI.
 * 2. User-friendly feature display names in the restart prompt tracker (without pulling Compose into hooked WhatsApp process).
 */
object FeatureCatalog {

    val ALL_FEATURES: List<FeatureItem> = listOf(
        // --- PRIVACY TAB (Tab 1), Sub-tab "privacy" ---
        FeatureItem("always_online", "Always Online", "Show you online even if you minimize WhatsApp (Doesn't work if you remove it from recents)", "Presence & Online Visibility", 1, "privacy", "Privacy"),
        FeatureItem("freezelastseen", "Freeze Last Seen", "Your last seen time will be frozen", "Presence & Online Visibility", 1, "privacy", "Privacy"),
        FeatureItem("ghostmode_t", "Hide Typing", "Users cannot see that you are typing", "Presence & Online Visibility", 1, "privacy", "Privacy"),
        FeatureItem("ghostmode_r", "Hide Recording Audio", "Users cannot see that you are recording audio", "Presence & Online Visibility", 1, "privacy", "Privacy"),
        FeatureItem("stealth_status_view", "Hide Status View", "View statuses without users knowing", "Presence & Online Visibility", 1, "privacy", "Privacy"),
        FeatureItem("hide_read_receipts", "Hide Blue Ticks", "View messages within conversation screen without users knowing", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("hideread_group", "Hide Blue Tick in Groups", "View messages in groups screen without users knowing", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("blueonreply", "Send Blue Ticks upon Reply", "Sends blue ticks after replying to a message", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("seentick", "Show Button to send blue tick", "Show Button to send blue tick (mark as read/viewed)", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("hide_delivery_receipts", "Hide Delivered", "Users will not know that their messages have been delivered to you", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("hide_seen_receipts", "Hide audio seen", "Hides the sending of audio reading when listening to it", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("hideonceseen", "Hide View Once Seen", "Hide that view one media has been seen", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("hide_forwarded_tag", "Hide \"Forwarded\" Tag", "Forward messages without the tag \"Forwarded\"", "Message & Delivery Receipts", 1, "privacy", "Privacy"),
        FeatureItem("anti_revoke", "Anti-Revoke Messages", "Messages will not be deleted for you", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("hide_anti_revoke", "Add Hide Anti-Revoke to Chat Menu", "Add option to conversation menu to hide deleted messages for that chat", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("preserve_own_revoke", "Keep My Revoked Messages", "Keep your local copy after Delete for Everyone while deleting it for recipients", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("antirevokestatus", "Anti-Delete Status", "View statuses that users have since deleted", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("anti_view_once", "Unlimited View Once", "Allows you to open view once media multiple times", "Message Protection & Security", 1, "privacy", "Privacy"),
        FeatureItem("locked_chats_enhancer", "Enhanced Locked Chats", "Improve locked chats by hiding notifications and contacts from the contact list", "Message Protection & Security", 1, "privacy", "Privacy"),
        FeatureItem("typearchive", "Hide Archived Chats", "Hide archived chats, to access click 5 times or hold on the \"WhatsApp\" title", "Message Protection & Security", 1, "privacy", "Privacy"),
        FeatureItem("dnd_mode", "DND Mode", "When Do Not Disturb mode is on, you will be unable to send or receive messages", "Message Protection & Security", 1, "privacy", "Privacy"),
        FeatureItem("hide_chats", "Hide Locked Chats", "Hide locked chats, view them by holding WhatsApp title on home screen", "Message Protection & Security", 1, "privacy", "Privacy"),
        FeatureItem("custom_privacy", "Custom Privacy per contact", "Activate the custom privacy button on the contact information screen", "Advanced Rules & Filtering", 1, "privacy", "Privacy"),
        FeatureItem("call_privacy", "Block Calls", "Block WhatsApp calls based on privacy type", "Advanced Rules & Filtering", 1, "privacy", "Privacy"),
        FeatureItem("autonext_status", "Disable Auto Skip Status", "Prevents the current status from advancing automatically to the next one", "Status Privacy", 1, "privacy", "Privacy"),
        FeatureItem("toast_viewed_status", "Show toast on viewed your status", "Shows a toast if someone views your status", "Status Privacy", 1, "privacy", "Privacy"),
        FeatureItem("antidisappearing", "Anti Disappearing Messages", "Temporary messages will not be deleted for you", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("toastdeleted", "Show toast notification on delete message", "Show toast notification if any contact deletes any message", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("toast_viewed_message", "Show toast on viewed your message", "Shows a toast if someone views your message", "Anti-Revoke & Deletion Defense", 1, "privacy", "Privacy"),
        FeatureItem("ghostmode", "Show Ghost Mode Button", "Show a Ghost Mode button on the home screen toolbar", "Home Menu Shortcuts", 1, "privacy", "Privacy"),
        FeatureItem("show_dndmode", "Show DND Button", "Show button for DND Mode on home screen toolbar", "Home Menu Shortcuts", 1, "privacy", "Privacy"),
        FeatureItem("restartbutton", "Enable Restart Button", "Add button in Home Screen to Restart App", "Home Menu Shortcuts", 1, "privacy", "Privacy"),
        FeatureItem("open_wae", "Enable WAEX Button", "Add button in Home Screen or WhatsApp Settings to open Wa Enhancer", "Home Menu Shortcuts", 1, "privacy", "Privacy"),

        // --- PRIVACY TAB (Tab 1), Sub-tab "conversation" ---
        FeatureItem("message_bomber", "Message Bomber", "Send a short, delayed sequence of messages from inside a WhatsApp chat", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("anti_edit_messages", "Show Edited Message History", "Show edited message history when clicking \"Edited\" on a message", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("message_device_source", "Show Message Device Source", "Shows whether a message was sent from the primary device or a linked device", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("preserve_delete_for_me", "Delete (for me)", "Retain messages locally when Delete for Me is selected", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("revokeallmessages", "Increase limit of \"Delete for everyone\" option", "Increases the limit to 3 days in the option to delete messages for everyone", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("removeforwardlimit", "Remove Forward Limit", "Remove forward limit for 5 chats (normal) and 1 chat (multiple times)", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("sticker_confirm_alert", "Confirmation Before Sending Sticker", "Show a dialog before sending the sticker", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("removeseemore", "Remove \"See More\" Button", "Disable \"See More\" button and show all long message", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("stamp_copied_message", "Remove Stamp from Copied Messages", "Removes name and date when copying more than one message", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("doubletap2like", "Enable Double Click to React", "Activates the possibility of double-clicking on the message to react it", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("doubletap2like_emoji", "Custom Reaction Emoji", "Change the default emoji sent when double-clicking on a message", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("jump_to_first_message", "Jump to First Message", "Add a button to skip the first message in the conversations screen", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("copy_status_text", "Enable Copy Status", "Activates the possibility of copying the description and caption of statuses by holding on them", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("inline_translation", "Enable Google Translate", "Replaces Whatsapp's native translator with Google Translate", "Message Controls", 1, "conversation", "Conversation"),
        FeatureItem("direct_chat_dialer", "New Chat", "Message numbers directly without saving them to contacts", "Chat & Group Utilities", 1, "conversation", "Conversation"),
        FeatureItem("unlimited_pinned_chats", "Disable Pinned Chats Limit", "Disable limit of 3 pinned chats", "Chat & Group Utilities", 1, "conversation", "Conversation"),
        FeatureItem("broadcast_tag", "Show chat broadcast icon", "Shows an icon if the contact sent a message via broadcast", "Chat & Group Utilities", 1, "conversation", "Conversation"),
        FeatureItem("group_admin_tools", "Show Admin Group Icon", "Show an admin icon next to the name of the user who is the group admin", "Chat & Group Utilities", 1, "conversation", "Conversation"),
        FeatureItem("call_type_controller", "Enable selection of call type", "Show an option to select whether you want a call via phone or WhatsApp", "Chat & Group Utilities", 1, "conversation", "Conversation"),
        FeatureItem("status_text_composer", "Custom colors for text status", "Press and hold on the color selector in the status to customize it", "Chat & Group Utilities", 1, "conversation", "Conversation"),

        // --- MEDIA TAB (Tab 2) ---
        FeatureItem("status_downloader", "Download and Share Status", "Shows two buttons to share and download status", "Media Quality & Status", 2, null, "Media"),
        FeatureItem("media_upload_quality", "HD Quality Images & Videos", "Send images and videos in HD quality by default", "Media Quality & Status", 2, null, "Media"),
        FeatureItem("send_audio_as_voice_status", "Audio to Voice Status", "Pick a local audio file and publish it as a voice status", "Media Quality & Status", 2, null, "Media"),
        FeatureItem("status_video_splitter", "Status Video Splitter", "Split long videos into 30, 60, or 90 second status clips", "Media Quality & Status", 2, null, "Media"),
        FeatureItem("file_size_spoofer", "File Size Spoofer", "Set the file size displayed to the recipient from WhatsApp's send preview", "Media Quality & Status", 2, null, "Media"),
        FeatureItem("call_recording", "Call Recording", "Record incoming and outgoing calls (Voice & Video) as audio", "Media Utility & Downloader", 2, null, "Media"),
        FeatureItem("download_profile", "Download Profile Photo", "Download full-resolution profile pictures directly", "Media Utility & Downloader", 2, null, "Media"),
        FeatureItem("download_view_once", "Download View Once", "Show button to download view once media", "Media Utility & Downloader", 2, null, "Media"),
        FeatureItem("media_preview", "Enable Media Preview", "Add a button to preview media in a temporary file", "Media Utility & Downloader", 2, null, "Media"),

        // --- AUTOMATION TAB (Tab 3), Sub-tab "automation" ---
        FeatureItem("always_typing", "Hide Typing", "Users cannot see that you are typing", "Automation", 3, "automation", "Automation"),
        FeatureItem("tasker_integration", "Enable Tasker Automation", "Enables using intents to receive and send messages in Tasker", "Automation", 3, "automation", "Automation"),

        // --- AUTOMATION TAB (Tab 3), Sub-tab "ai" ---
        FeatureItem("voice_transcription", "Audio Transcription", "Enable WhatsApp audio transcription with Groq AI or AssemblyAI", "Audio & AI", 3, "ai", "Automation"),

        // --- STYLES TAB (Tab 4), Sub-tab "appearance" ---
        FeatureItem("bubble_colors", "Change Bubble Colors", "Change Bubble Color on Conversation Screen", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("custom_theme", "Custom Theme CSS", "Customize your WhatsApp using CSS styles", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("custom_time_format", "Seconds on Timestamp", "Show seconds next to any timestamp in the WhatsApp app", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("custom_toolbar", "New Settings Style", "Enable the new settings style, with profile photo on home screen toolbar", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("custom_view_dpi", "Change Default DPI", "Change the DPI setting for the application. Use 0 to reset to default.", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("seen_tick_customization", "View Seen Tick", "Show an icon if the message view was sent to the recipient or unique view was seen", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("floating_bottom_bar", "Floating Bottom Bar", "Enable iOS-style floating bottom navigation bar", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("unlock_premium_customization", "Unlock WA Plus", "Unlock official WhatsApp Plus subscription features including app icons, themes, and premium stickers.", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("filter_items", "Filter Items By ID", "Remove or customize WhatsApp views matching specific IDs (Gone, Change Color, Opacity, Resize)", "Visual Styles", 4, "appearance", "Styles"),
        FeatureItem("custom_filters", "Custom Appearance Filters", "Enable or disable custom view ID filter rules", "Visual Styles", 4, "appearance", "Styles"),

        // --- STYLES TAB (Tab 4), Sub-tab "layout" ---
        FeatureItem("dotonline", "Show Online Dot in Conversation List", "Show a green online dot on home screen", "Conversation List Activity & Presence", 4, "layout", "Styles"),
        FeatureItem("showonlinetext", "Show Online/Last seen in Conversation List", "Show a text online or last seen on home screen", "Conversation List Activity & Presence", 4, "layout", "Styles"),
        FeatureItem("typing_online_toasts", "Show toast on contact online", "Show a toast when a contact is online", "Conversation List Activity & Presence", 4, "layout", "Styles"),
        FeatureItem("channels_enhancements", "Remove Channel Recomendations", "Remove Channel Recomendations from tab Status", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("chat_filters", "Enable filter chats for type", "Show options to filter chats for groups, contacts and unseen messages", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("hide_ui_tabs", "Hide Tabs on Home", "Hide tabs on the home screen such as Updates, Communities and Calls", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("instagram_status_layout", "Enable IGStatus on Home Screen", "Show status style Instagram in Home Screen", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("separate_groups_tabs", "Separate Groups", "Separate your chats by: Groups, Private Chats, Status, Calls, Communities", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("quick_home_menu", "Quick Action Home Menu", "Add quick actions to home long-press", "Home Layout & Navigation", 4, "layout", "Styles"),
        FeatureItem("contact_blocked_verify", "Show Contact Added Status in Conversation", "This option verifies whether the contact added you or has a public profile photo", "Utilities & Data", 4, "layout", "Styles"),
        FeatureItem("miscellaneous_enhancements", "Disable Screen off on proximity sensor", "Disable Screen off on proximity sensor to the whole WhatsApp", "Utilities & Data", 4, "layout", "Styles"),

        // --- SETTINGS & SYSTEM ---
        FeatureItem("show_hook_toast", "Show Hook Injection Toast", "Show or hide the injecting hooks notification when WhatsApp opens", "System & Compatibility", -1, null, "Settings"),
        FeatureItem("show_restart_sheet", "Show Restart Sheet", "Prompt to restart WhatsApp after preference changes so hooks are re-injected", "System & Compatibility", -1, null, "Settings"),
        FeatureItem("supported_versions", "Supported WhatsApp Versions", "Manage verified WhatsApp and WA Business versions & wildcards", "System & Compatibility", -1, null, "Settings"),
        FeatureItem("bypass_version_check", "Disable Version Check", "Disables the supported version check of WhatsApp", "System & Compatibility", -1, null, "Settings"),
        FeatureItem("bootloader_spoofer", "Bootloader Spoofer", "Spoof verified boot attestation for WhatsApp integrity checks", "System & Compatibility", -1, null, "Settings"),

        // --- PREMIUM (Paywall) ---
        FeatureItem("license_verification", "License Verification & Activation", "Manages license key entry and validation", "Premium", -1, null, "Premium"),
        FeatureItem("pro_features_unlock", "Pro Feature Management", "Dynamic locking/unlocking of premium features", "Premium", -1, null, "Premium")
    )

    private val KEY_TO_ITEM: Map<String, FeatureItem> = ALL_FEATURES.associateBy { it.key }

    // Aliases to handle legacy or alternative preference keys
    private val ALIASES: Map<String, String> = mapOf(
        "freeze_last_seen" to "freezelastseen",
        "antirevoke" to "anti_revoke",
        "downloadstatus" to "status_downloader",
        "downloadviewonce" to "download_view_once",
        "custom_css" to "custom_theme",
        "change_dpi" to "custom_view_dpi",
        "open_waex" to "open_wae"
    )

    @JvmStatic
    fun findByKey(key: String?): FeatureItem? {
        if (key == null) return null
        KEY_TO_ITEM[key]?.let { return it }
        val canonicalKey = ALIASES[key]
        return if (canonicalKey != null) KEY_TO_ITEM[canonicalKey] else null
    }

    @JvmStatic
    fun getTitle(key: String?): String? {
        return findByKey(key)?.title
    }
}
