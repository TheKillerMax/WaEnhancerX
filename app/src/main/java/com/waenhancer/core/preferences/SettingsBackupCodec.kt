package com.waenhancer.core.preferences

import android.content.Context
import com.waenhancer.config.PreferenceSchema
import com.waenhancer.config.PreferenceStores
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.nio.charset.StandardCharsets
import java.util.Collections
import java.util.LinkedHashSet
import java.util.Locale

/**
 * Versioned WAEX settings container with support for both binary (.waex) and legacy JSON backups.
 */
object SettingsBackupCodec {
    const val EXTENSION = "waex"
    const val MIME_TYPE = "application/vnd.waenhancer.settings"

    private val magic = byteArrayOf(0x57, 0x41, 0x45, 0x58, 0x43, 0x46, 0x47, 0x00) // WAEXCFG\0
    private const val VERSION = 1
    private const val MAX_ENTRIES = 10_000
    private const val MAX_BYTES = 8 * 1024 * 1024

    private val BLOCKED_KEYS = Collections.unmodifiableSet(
        hashSetOf(
            "keybox", "keybox_xml", "private_key", "certificate", "certificates",
            "license_key", "license_token", "tg_username", "encrypted_config",
            "is_pro_verified", "expires_at", "pro_plugin_path", "pro_plugin_lib_path",
            "github_token", "gh_public_token", "tasker_secret", "installation_id",
            "module_heartbeat", "last_crash", "crash_stacktrace"
        )
    )

    private val LEGACY_ALIASES: Map<String, String> = mapOf(
        // General & Theme aliases
        "colors_customization" to "changecolor",
        "custom_primary_color" to "primary_color",
        "showname" to "shownamehome",
        "showbio" to "showbiohome",
        "show_name_home" to "shownamehome",
        "show_bio_home" to "showbiohome",
        "separate_groups" to "separategroups",
        "separate_groups_counter" to "separategroups_counter_type",
        "separate_groups_tabs" to "separategroups",
        "statusdowload" to "downloadstatus",
        "download_status" to "downloadstatus",
        "status_downloader" to "downloadstatus",
        "locked_chats_enhancer" to "lockedchats_enhancer",
        "show_message_device_source" to "message_device_source",
        "toast_viewer" to "toast_viewed_message",
        "audio_transcript" to "audio_transcription",
        "voice_transcription" to "audio_transcription",
        "voice_status_enhancement" to "send_audio_as_voice_status",
        "freeze_last_seen" to "freezelastseen",
        "ghostmode_enabled" to "ghostmode",
        "bubble_colors" to "bubble_color",
        "custom_theme" to "custom_css",
        "custom_time_format" to "segundos",
        "custom_toolbar" to "novaconfig",
        "custom_view_dpi" to "change_dpi",
        "seen_tick_customization" to "seentick",
        "channels_enhancements" to "removechannel_rec",
        "chat_filters" to "chatfilter",
        "hide_ui_tabs" to "hidetabs",
        "instagram_status_layout" to "igstatus",
        "quick_home_menu" to "show_home_menu",
        "contact_blocked_verify" to "verify_blocked_contact",
        "miscellaneous_enhancements" to "disable_sensor_proximity",
        "high_res_media" to "imagequality",
        "direct_chat_button" to "newchat",
        "status_caption_copy" to "copystatus",
        "copy_status_text" to "copystatus",
        "jump_to_first_message" to "go_to_first_message",
        "dnd_mode" to "show_dndmode",
        "stealth_view_status" to "hidestatusview",
        "stealth_status_view" to "hidestatusview",
        "anti_view_once" to "downloadviewonce",
        "anti_view_once_media" to "downloadviewonce",
        "anti_edit_messages" to "antieditmessages",
        "anti_revoke" to "antirevoke",
        "online_status_indicator" to "dotonline",
        "typing_online_toasts" to "typing_privacy",
        "unlimited_pinned_chats" to "pinnedlimit",
        "chat_limits_bypass" to "removeforwardlimit",
        "unlimited_video_status" to "status_video_splitter",
        "status_text_composer" to "status_style",
        "voice_note_speed_modifier" to "voicenote_speed",
        "group_admin_tools" to "admin_grp",
        "hide_chats" to "lockedchats_enhancer",
        "hide_read_receipts" to "hideread",
        "hide_seen_receipts" to "hidereceipt",
        "hide_delivery_receipts" to "hidereceipt_ios",
        "hide_forwarded_tag" to "hidetag",
        "tasker_integration" to "tasker",
        "sticker_confirm_alert" to "alertsticker",
        "floating_nav_bar" to "floating_bottom_bar",
        "floating_bottom_bar_scroll_hide" to "floating_bottom_bar_scroll_hide_mode",
        "call_recording_enable" to "call_recording_enabled"
    )

    fun encode(context: Context, output: OutputStream): Int {
        val records = PreferenceSchema.exportableKeys().sorted().mapNotNull { key ->
            val value = PreferenceStores.read(context, key) ?: return@mapNotNull null
            val entry = PreferenceSchema.entry(key) ?: return@mapNotNull null
            normalizeForKey(key, entry.type, value)?.let { Record(key, entry.type, it) }
        }

        DataOutputStream(BufferedOutputStream(output)).use { out ->
            out.write(magic)
            out.writeInt(VERSION)
            out.writeLong(System.currentTimeMillis())
            out.writeInt(records.size)
            records.forEach { record ->
                writeText(out, record.key)
                out.writeByte(record.type.ordinal)
                when (record.type) {
                    PreferenceSchema.Type.BOOLEAN -> out.writeBoolean(record.value as Boolean)
                    PreferenceSchema.Type.STRING -> writeText(out, record.value as String)
                    PreferenceSchema.Type.STRING_SET -> {
                        val values = (record.value as Set<*>).filterIsInstance<String>().sorted()
                        out.writeInt(values.size)
                        values.forEach { writeText(out, it) }
                    }
                    PreferenceSchema.Type.INT -> out.writeInt((record.value as Number).toInt())
                    PreferenceSchema.Type.LONG -> out.writeLong((record.value as Number).toLong())
                    PreferenceSchema.Type.FLOAT -> out.writeFloat((record.value as Number).toFloat())
                }
            }
        }
        return records.size
    }

    fun decode(context: Context, input: InputStream): Int {
        val bytes = input.use { it.readBytes() }
        require(bytes.isNotEmpty()) { "Backup is empty" }
        require(bytes.size <= MAX_BYTES) { "Backup exceeds the allowed size limit" }

        val records = if (bytes.size >= magic.size && bytes.take(magic.size).toByteArray().contentEquals(magic)) {
            decodeBinary(bytes)
        } else {
            decodeJson(bytes)
        }

        require(records.isNotEmpty()) { "No valid settings found in backup" }

        val publicEditor = PreferenceStores.publicStore(context).edit()
        val privateEditor = PreferenceStores.privateStore(context).edit()
        records.forEach { record ->
            val schema = PreferenceSchema.entry(record.key)!!
            val editor = if (schema.store == PreferenceSchema.Store.PRIVATE) privateEditor else publicEditor
            when (record.type) {
                PreferenceSchema.Type.BOOLEAN -> editor.putBoolean(record.key, record.value as Boolean)
                PreferenceSchema.Type.STRING -> editor.putString(record.key, record.value as String)
                PreferenceSchema.Type.STRING_SET -> @Suppress("UNCHECKED_CAST")
                editor.putStringSet(record.key, record.value as Set<String>)
                PreferenceSchema.Type.INT -> editor.putInt(record.key, record.value as Int)
                PreferenceSchema.Type.LONG -> editor.putLong(record.key, record.value as Long)
                PreferenceSchema.Type.FLOAT -> editor.putFloat(record.key, record.value as Float)
            }
        }
        check(privateEditor.commit() && publicEditor.commit()) { "Could not save imported settings" }
        return records.size
    }

    private fun decodeBinary(bytes: java.io.ByteArrayInputStream.() -> Unit = {}): List<Record> {
        throw UnsupportedOperationException()
    }

    private fun decodeBinary(bytes: ByteArray): List<Record> {
        return DataInputStream(BufferedInputStream(bytes.inputStream())).use { source ->
            val actualMagic = ByteArray(magic.size)
            source.readFully(actualMagic)
            require(actualMagic.contentEquals(magic)) { "Not a WAEX settings file" }
            require(source.readInt() == VERSION) { "Unsupported WAEX settings version" }
            source.readLong() // creation time
            val count = source.readInt()
            require(count in 0..MAX_ENTRIES) { "Invalid settings record count" }
            buildList(count) {
                repeat(count) {
                    val rawKey = readText(source)
                    // Binary WAEX backups already contain canonical schema keys.
                    // Never reinterpret a valid key through a legacy JSON alias.
                    val key = resolveKey(rawKey, legacyJson = false)
                    val typeOrdinal = source.readUnsignedByte()
                    val type = PreferenceSchema.Type.entries.getOrNull(typeOrdinal)
                        ?: throw IllegalArgumentException("Unknown settings value type")

                    val value: Any = when (type) {
                        PreferenceSchema.Type.BOOLEAN -> source.readBoolean()
                        PreferenceSchema.Type.STRING -> readText(source)
                        PreferenceSchema.Type.STRING_SET -> {
                            val size = source.readInt()
                            require(size in 0..MAX_ENTRIES) { "Invalid string-set size" }
                            buildSet(size) { repeat(size) { add(readText(source)) } }
                        }
                        PreferenceSchema.Type.INT -> source.readInt()
                        PreferenceSchema.Type.LONG -> source.readLong()
                        PreferenceSchema.Type.FLOAT -> source.readFloat()
                    }

                    if (key != null) {
                        val schema = PreferenceSchema.entry(key)
                        if (schema != null && schema.isExportable()) {
                            val normalized = normalizeForKey(key, schema.type, value)
                            if (normalized != null) {
                                add(Record(key, schema.type, normalized))
                            }
                        }
                    }
                }
            }
        }
    }

    private fun decodeJson(bytes: ByteArray): List<Record> {
        val root = try {
            JSONObject(String(bytes, StandardCharsets.UTF_8))
        } catch (e: JSONException) {
            throw IllegalArgumentException("Backup is neither a valid WAEX binary nor a valid JSON backup file", e)
        }

        val legacy = !root.has("schemaVersion")
        val source: JSONObject = if (legacy) {
            root
        } else {
            root.optJSONObject("settings") ?: throw IllegalArgumentException("Backup JSON does not contain settings object")
        }

        val records = mutableListOf<Record>()
        val keys = source.keys()
        while (keys.hasNext()) {
            val rawKey = keys.next()
            // Only unversioned v1 JSON files use the old alias migration rules.
            val key = resolveKey(rawKey, legacyJson = legacy) ?: continue
            if (isSensitive(key)) continue

            val schema = PreferenceSchema.entry(key) ?: continue
            if (!schema.isExportable()) continue

            val rawVal = source.opt(rawKey) ?: continue
            val decodedValue = decodeJsonValue(rawVal, legacy) ?: continue
            val normalized = normalizeForKey(key, schema.type, decodedValue) ?: continue
            records.add(Record(key, schema.type, normalized))
        }
        return records
    }

    private fun decodeJsonValue(raw: Any, legacy: Boolean): Any? {
        if (raw is JSONObject) {
            val type = raw.optString("type", "").lowercase(Locale.ROOT)
            val value = raw.opt("value") ?: return null
            return when (type) {
                "boolean" -> (value as? Boolean) ?: (value.toString() == "true")
                "integer", "int" -> asNumber(value)?.toInt()
                "long" -> asNumber(value)?.toLong()
                "double", "float" -> asNumber(value)?.toFloat()
                "hashset", "string_set", "jsonarray" -> toStringSet(value)
                "string" -> value.toString()
                else -> value
            }
        }
        return if (legacy) {
            when (raw) {
                is JSONArray -> toStringSet(raw)
                is Boolean, is Number, is String -> raw
                else -> raw.toString()
            }
        } else {
            raw
        }
    }

    private fun asNumber(value: Any): Number? {
        if (value is Number) return value
        return try {
            value.toString().toDoubleOrNull()
        } catch (e: Exception) {
            null
        }
    }

    private fun toStringSet(value: Any): Set<String>? {
        return when (value) {
            is JSONArray -> {
                val set = LinkedHashSet<String>()
                for (i in 0 until value.length()) {
                    set.add(value.optString(i))
                }
                set
            }
            is Set<*> -> value.filterIsInstance<String>().toSet()
            is List<*> -> value.filterIsInstance<String>().toSet()
            else -> null
        }
    }

    private fun resolveKey(originalKey: String, legacyJson: Boolean): String? {
        val original = PreferenceSchema.entry(originalKey)
        // Binary backups and versioned JSON contain canonical names. A current
        // preference must never be silently rewritten into another setting.
        if (!legacyJson && original != null) return originalKey

        // Preserve legacy JSON mappings where the old and new schema types are
        // compatible. Do not turn a Boolean into a String/Float or lose its value.
        val mappedKey = LEGACY_ALIASES[originalKey]
        val mapped = mappedKey?.let(PreferenceSchema::entry)
        if (mapped != null && (original == null || original.type == mapped.type)) {
            return mappedKey
        }
        return if (original != null) originalKey else null
    }

    private fun isSensitive(key: String?): Boolean {
        if (key == null) return true
        if (PreferenceSchema.isSecret(key)) return true
        val normalized = key.lowercase(Locale.ROOT)
        if (BLOCKED_KEYS.contains(normalized)) return true
        return normalized.contains("private_key") ||
                normalized.contains("secret") ||
                normalized.contains("token") ||
                normalized.contains("certificate") ||
                normalized.contains("keybox") ||
                normalized.contains("license") ||
                normalized.contains("plugin_path") ||
                normalized.contains("classloader") ||
                normalized.contains("heartbeat") ||
                normalized.contains("crash_stack")
    }

    private fun writeText(out: DataOutputStream, value: String) {
        val bytes = value.toByteArray(Charsets.UTF_8)
        require(bytes.size <= MAX_BYTES) { "Settings value is too large" }
        out.writeInt(bytes.size)
        out.write(bytes)
    }

    private fun readText(input: DataInputStream): String {
        val size = input.readInt()
        require(size in 0..MAX_BYTES) { "Invalid settings value length" }
        return ByteArray(size).also(input::readFully).toString(Charsets.UTF_8)
    }

    /** Restore hex RGB/ARGB strings written by earlier UI versions for this INT key. */
    private fun normalizeForKey(key: String, type: PreferenceSchema.Type, value: Any): Any? {
        if (key == "deleted_message_color" && type == PreferenceSchema.Type.INT && value is String) {
            val hex = value.trim()
            if (hex.matches(Regex("#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?"))) {
                val parsed = hex.substring(1).toLong(16)
                return (if (hex.length == 7) parsed or 0xFF000000L else parsed).toInt()
            }
        }
        return normalize(type, value)
    }

    private fun normalize(type: PreferenceSchema.Type, value: Any): Any? = when (type) {
        PreferenceSchema.Type.BOOLEAN -> when (value) {
            is Boolean -> value
            is Number -> value.toInt() != 0
            is String -> value == "1" || value.equals("true", ignoreCase = true)
            else -> null
        }
        PreferenceSchema.Type.STRING -> when (value) {
            is Set<*> -> value.filterIsInstance<String>().joinToString(",")
            else -> value.toString()
        }
        PreferenceSchema.Type.STRING_SET -> when (value) {
            is Set<*> -> value.filterIsInstance<String>().toSet()
            is List<*> -> value.filterIsInstance<String>().toSet()
            is String -> if (value.isEmpty()) emptySet() else value.split(",").map { it.trim() }.toSet()
            else -> null
        }
        PreferenceSchema.Type.INT -> when (value) {
            is Number -> value.toInt()
            is String -> value.toIntOrNull() ?: value.toFloatOrNull()?.toInt()
            else -> null
        }
        PreferenceSchema.Type.LONG -> when (value) {
            is Number -> value.toLong()
            is String -> value.toLongOrNull() ?: value.toFloatOrNull()?.toLong()
            else -> null
        }
        PreferenceSchema.Type.FLOAT -> when (value) {
            is Number -> value.toFloat()
            is String -> value.toFloatOrNull()
            else -> null
        }
    }

    private data class Record(val key: String, val type: PreferenceSchema.Type, val value: Any)
}
