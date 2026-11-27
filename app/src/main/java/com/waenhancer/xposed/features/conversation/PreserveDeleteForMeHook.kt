package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.SharedPreferences
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import com.waenhancer.xposed.bridge.client.HookProviderIpc
import android.os.Bundle
import android.os.SystemClock
import com.waenhancer.xposed.core.BaseFeature
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import com.waenhancer.xposed.utils.HookErrors
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import java.io.File
import java.lang.reflect.Member
import java.util.concurrent.Executors

/**
 * Feature: Preserve "Delete For Me" Messages.
 *
 * Intercepts message deletion requests when the user clicks "Delete For Me".
 * Resolves contact display names, sender names, & group subjects from WhatsApp's wa.db & msgstore.db,
 * copies the message to the Manager App vault, then allows WhatsApp to delete its own row.
 */
class PreserveDeleteForMeHook(
    context: Context,
    classLoader: ClassLoader,
    prefs: SharedPreferences
) : BaseFeature(context, classLoader, prefs) {

    override val name: String
        get() = "PreserveDeleteForMe"

    companion object {
        private const val TAG = "[WAEX:PreserveDeleteForMe]"
        private const val PREF_KEY = "preserve_delete_for_me"

        // Scope denotes a local request on this thread, not a persistence receipt.
        private val preservationWarningLock = Any()
        private var lastPreservationWarningAtElapsed = -1L
        private const val PRESERVATION_WARNING_INTERVAL_MS = 30_000L
        private val preservationExecutor = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "WAEX-PreserveDeleteForMe").apply { isDaemon = true }
        }

        /** Lets other database hooks distinguish a local Delete-for-me from a remote revoke. */
        @JvmStatic
        fun isDeleteForMeInProgress(): Boolean = DeleteOriginSession.inLocalRequest()
    }

    private var session: DeleteOriginSession? = null

    override fun hook() {
        // Registry holds a bridge lease for the entire install. No Method cache (including v7)
        // can attest the listener, constructor, field uses and local API together.
        val engine = DexSearchEngine.getInstance()
        engine.initialize(context)
        val bridge = checkNotNull(engine.bridge) { "Delete-for-me entry point unavailable" }
        // C03 proves the UI graph but not which of the two FMessage key fields is its own key.
        install(DexDeleteCode(bridge, classLoader), context.packageName == "com.whatsapp", null)
    }

    internal fun install(code: DeleteCode, personal: Boolean, keys: SelectedKeys?,
                        register: (Member, XC_MethodHook) -> Unit = { m, cb ->
                            checkNotNull(XposedBridge.hookMethod(m, cb))
                        }) {
        check(session == null)
        val route = try {
            DeleteRoute.resolve(code, personal)
        } catch (t: Throwable) {
            // The installation owner reports the message and prints the entire throwable.
            throw IllegalStateException("Delete-for-me route search failed: ${t.javaClass.simpleName}")
        } ?: error("Delete-for-me entry point unavailable")
        val next = DeleteOriginSession { isEnabled(PREF_KEY, false) }
        session = next
        when (route) {
            is DeleteRoute.Local -> {
                val reader = checkNotNull(keys) { "Delete-for-me selected message key contract unavailable" }
                next.installLocal(route, register) { captureSelectedMessages(it, reader) }
                // Do not also inspect arbitrary SQLite deletes beneath a local API call.
            }
            is DeleteRoute.Store -> {
                next.installStore(route.method, register)
                check(hookDatabaseDeleteForMe()) { "Delete-for-me database interception unavailable" }
            }
        }
        next.activate()
    }

    override fun unhookAll() {
        session?.close()
        session = null
        super.unhookAll()
    }

    private fun hookDatabaseDeleteForMe(): Boolean {
        return try {
            XposedBridge.hookAllMethods(
                SQLiteDatabase::class.java,
                "delete",
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        if (!isEnabled(PREF_KEY, false)) return
                        if (session?.inStoreRequest() != true) return

                        val table = param.args.getOrNull(0) as? String ?: return
                        if (table != "message") return

                        val where = param.args.getOrNull(1) as? String ?: return
                        val whereArgs = param.args.getOrNull(2) as? Array<*>

                        val db = param.thisObject as? SQLiteDatabase ?: return

                        try {
                            val sqlArgs = whereArgs?.map { it?.toString() ?: "" }?.toTypedArray() ?: emptyArray()
                            val querySql = "SELECT _id, key_id, chat_row_id, from_me, message_type, text_data, timestamp, sender_jid_row_id FROM message WHERE $where"

                            var hadUnconfirmedMessage = false
                            db.rawQuery(querySql, sqlArgs).use { cursor ->
                                if (cursor != null && cursor.moveToFirst()) {
                                    do {
                                        val keyId = cursor.getString(1)
                                        val chatRowId = cursor.getLong(2)
                                        val fromMe = cursor.getInt(3) == 1
                                        val msgType = cursor.getInt(4)
                                        val textData = cursor.getString(5) ?: ""
                                        val msgTs = cursor.getLong(6)
                                        val senderJidRowId = if (cursor.columnCount > 7) cursor.getLong(7) else 0L

                                        if (!keyId.isNullOrEmpty() && msgType != 15) {
                                            val now = System.currentTimeMillis()
                                            val chatJid = resolveChatJid(db, chatRowId)
                                            val isGroup = chatJid.contains("@g.us")
                                            val chatDisplayName = resolveChatDisplayName(context, db, chatRowId, chatJid)
                                            val senderDisplayName = if (isGroup)
                                                resolveSenderDisplayName(context, db, senderJidRowId, chatDisplayName)
                                            else chatDisplayName

                                            if (!dispatchToManagerApp(
                                                jid = chatJid,
                                                chatName = chatDisplayName,
                                                senderName = senderDisplayName,
                                                msgId = keyId,
                                                text = textData,
                                                timestamp = if (msgTs > 0) msgTs else now,
                                                fromMe = fromMe,
                                                isGroup = isGroup
                                            )) hadUnconfirmedMessage = true
                                        }
                                    } while (cursor.moveToNext())
                                }
                            }
                            if (hadUnconfirmedMessage) warnPreservationUnconfirmed()
                        } catch (t: Throwable) {
                            XposedBridge.log("$TAG Error inspecting message before delete: ${t.javaClass.simpleName}")
                        }
                    }
                }
            ).isNotEmpty()
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Error installing DB Delete-For-Me hook: ${t.javaClass.simpleName}")
            false
        }
    }

    private fun resolveChatJid(db: SQLiteDatabase, chatRowId: Long): String {
        if (chatRowId <= 0) return "Unknown"
        try {
            val sql = "SELECT raw_string FROM jid WHERE _id = (SELECT jid_row_id FROM chat WHERE _id = ?)"
            db.rawQuery(sql, arrayOf(chatRowId.toString())).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    val raw = cursor.getString(0)
                    if (!raw.isNullOrEmpty()) return raw
                }
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }
        return "chat_$chatRowId"
    }

    private fun resolveSenderDisplayName(
        ctx: Context,
        msgstoreDb: SQLiteDatabase,
        senderJidRowId: Long,
        fallback: String
    ): String {
        if (senderJidRowId <= 0) return fallback
        try {
            var rawJid = ""
            var userPart = ""
            msgstoreDb.rawQuery("SELECT raw_string, user FROM jid WHERE _id = ?", arrayOf(senderJidRowId.toString())).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    rawJid = cursor.getString(0) ?: ""
                    userPart = cursor.getString(1) ?: ""
                }
            }
            if (rawJid.isNotBlank()) {
                val resolved = resolveUserDisplayName(ctx, msgstoreDb, rawJid, userPart)
                if (resolved.isNotBlank()) return resolved
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }
        return fallback
    }

    private fun resolveChatDisplayName(
        ctx: Context,
        msgstoreDb: SQLiteDatabase,
        chatRowId: Long,
        rawJid: String
    ): String {
        // 1. If group chat, get subject from chat table in msgstore.db
        try {
            msgstoreDb.rawQuery("SELECT subject FROM chat WHERE _id = ?", arrayOf(chatRowId.toString())).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    val subject = cursor.getString(0)
                    if (!subject.isNullOrBlank()) return subject
                }
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }

        val userPart = rawJid.substringBefore("@")
        return resolveUserDisplayName(ctx, msgstoreDb, rawJid, userPart)
    }

    private fun resolveUserDisplayName(
        ctx: Context,
        msgstoreDb: SQLiteDatabase,
        rawJid: String,
        userPart: String
    ): String {
        var resolvedPhoneJid: String? = null
        var resolvedPhoneUser: String? = null
        val cleanJid = if (rawJid.contains("@")) rawJid else "$rawJid@lid"

        // 1. Check jid_map in msgstore.db (LID -> Phone JID)
        try {
            val resolvePhoneSql = """
                SELECT j2.raw_string, j2.user 
                FROM jid_map jm
                JOIN jid j1 ON jm.lid_row_id = j1._id
                JOIN jid j2 ON jm.jid_row_id = j2._id
                WHERE j1.raw_string = ? OR j1.user = ?
            """.trimIndent()
            msgstoreDb.rawQuery(resolvePhoneSql, arrayOf(cleanJid, userPart)).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    resolvedPhoneJid = cursor.getString(0)
                    resolvedPhoneUser = cursor.getString(1)
                }
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }

        // 2. Query wa.db (wa_contacts table)
        try {
            val waDbFile = File(ctx.filesDir.parentFile, "databases/wa.db")
            if (waDbFile.exists()) {
                SQLiteDatabase.openDatabase(waDbFile.absolutePath, null, SQLiteDatabase.OPEN_READONLY).use { waDb ->
                    val querySql = "SELECT display_name, wa_name, sort_name, number FROM wa_contacts WHERE jid = ? OR jid = ? OR number = ? OR number = ? OR number LIKE ?"
                    val params = arrayOf(
                        rawJid,
                        resolvedPhoneJid ?: "",
                        userPart,
                        resolvedPhoneUser ?: "",
                        "%${resolvedPhoneUser ?: userPart}%"
                    )
                    waDb.rawQuery(querySql, params).use { cursor ->
                        if (cursor != null && cursor.moveToFirst()) {
                            val displayName = cursor.getString(0)
                            val waName = cursor.getString(1)
                            val sortName = cursor.getString(2)
                            val number = cursor.getString(3)

                            if (!displayName.isNullOrBlank() && !displayName.all { it.isDigit() }) return displayName
                            if (!waName.isNullOrBlank() && !waName.all { it.isDigit() }) return waName
                            if (!sortName.isNullOrBlank() && !sortName.all { it.isDigit() }) return sortName
                            if (!displayName.isNullOrBlank()) return displayName
                            if (!number.isNullOrBlank()) return "+$number"
                        }
                    }
                }
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }

        // 3. Check verified business names in wa.db
        try {
            val waDbFile = File(ctx.filesDir.parentFile, "databases/wa.db")
            if (waDbFile.exists()) {
                SQLiteDatabase.openDatabase(waDbFile.absolutePath, null, SQLiteDatabase.OPEN_READONLY).use { waDb ->
                    waDb.rawQuery("SELECT verified_name FROM wa_vnames WHERE jid = ? OR jid = ?", arrayOf(rawJid, resolvedPhoneJid ?: "")).use { cursor ->
                        if (cursor != null && cursor.moveToFirst()) {
                            val vname = cursor.getString(0)
                            if (!vname.isNullOrBlank()) return vname
                        }
                    }
                }
            }
        } catch (ignored: Throwable) { HookErrors.swallowed("PreserveDeleteForMeHook", ignored) }

        if (!resolvedPhoneUser.isNullOrBlank()) {
            return "+$resolvedPhoneUser"
        }

        return if (userPart.all { it.isDigit() } && userPart.length in 10..15) {
            "+$userPart"
        } else {
            userPart
        }
    }

    private fun warnPreservationUnconfirmed() {
        synchronized(preservationWarningLock) {
            val now = SystemClock.elapsedRealtime()
            val previous = lastPreservationWarningAtElapsed
            if (previous >= 0L && now >= previous &&
                now - previous < PRESERVATION_WARNING_INTERVAL_MS) return
            lastPreservationWarningAtElapsed = now
        }
        // An old provider may have saved the message but returned no receipt.
        // Do not claim loss, expose its payload, or flood the log for a batch.
        XposedBridge.log("$TAG Message preservation was not confirmed by the manager")
    }

    private fun dispatchToManagerApp(
        jid: String,
        chatName: String,
        senderName: String,
        msgId: String,
        text: String,
        timestamp: Long,
        fromMe: Boolean,
        isGroup: Boolean
    ): Boolean {
        return try {
            val bundle = Bundle().apply {
                putString("jid", jid)
                putString("name", chatName)
                putString("senderName", senderName)
                putString("msgId", msgId)
                putString("text", text)
                putLong("timestamp", timestamp)
                putBoolean("fromMe", fromMe)
                putBoolean("isGroup", isGroup)
            }
            // This runs inside WhatsApp's delete path. Do not wait for the manager process or its
            // SQLite write; all metadata needed for preservation is already in the bundle.
            preservationExecutor.execute {
                try {
                    val acknowledgement = HookProviderIpc.call(
                        context,
                        "record_preserved_message",
                        null,
                        bundle
                    )
                    // The enqueue result only acknowledges scheduling. The manager's
                    // explicit persistence acknowledgement must be checked on this worker,
                    // without blocking WhatsApp's original Delete-for-me callback.
                    if (acknowledgement?.getBoolean("success", false) != true) {
                        warnPreservationUnconfirmed()
                    }
                } catch (_: Throwable) {
                    // Do not log private message content, message IDs or transport errors.
                    warnPreservationUnconfirmed()
                }
            }
            true
        } catch (_: Throwable) {
            false
        }
    }

    internal fun captureSelectedMessages(selection: Set<*>, reader: SelectedKeys): Boolean {
        try {
            // Historical vaults need not distinguish two chats carrying the same message id.
            val keys = selection.mapNotNull(reader::read).distinct().groupBy { it.id }
                .values.mapNotNull { it.singleOrNull() }
            if (keys.isEmpty()) {
                XposedBridge.log("$TAG Warning: selected message keys were not resolved")
                return false
            }

            val dbFile = context.getDatabasePath("msgstore.db")
            if (!dbFile.exists()) {
                XposedBridge.log("$TAG Warning: msgstore.db was not found")
                return false
            }

            var recognized = 0
            var enqueued = 0
            SQLiteDatabase.openDatabase(dbFile.absolutePath, null, SQLiteDatabase.OPEN_READONLY).use { db ->
                keys.forEach { key ->
                    db.rawQuery(
                        "SELECT m._id,m.key_id,m.chat_row_id,m.from_me,m.message_type,m.text_data," +
                            "m.timestamp,m.sender_jid_row_id,j.raw_string FROM message m " +
                            "LEFT JOIN chat c ON c._id=m.chat_row_id LEFT JOIN jid j ON j._id=c.jid_row_id " +
                            "WHERE m.key_id=? LIMIT 2", arrayOf(key.id)
                    ).use row@{ cursor ->
                        if (!cursor.moveToFirst() || !cursor.isLast || cursor.getInt(4) == 15 ||
                            cursor.getString(1) != key.id || cursor.getString(8) != key.chatJid ||
                            cursor.isNull(3) || cursor.getString(3) != (if (key.fromMe) "1" else "0")) return@row
                        val chatRowId = cursor.getLong(2)
                        val fromMe = key.fromMe
                        val chatJid = key.chatJid
                        val isGroup = chatJid.endsWith("@g.us")
                        val chatName = resolveChatDisplayName(context, db, chatRowId, chatJid)
                        val senderName = if (isGroup) {
                            resolveSenderDisplayName(context, db, cursor.getLong(7), chatName)
                        } else if (fromMe) {
                            "You"
                        } else {
                            chatName
                        }
                        if (dispatchToManagerApp(
                            jid = chatJid,
                            chatName = chatName,
                            senderName = senderName,
                            msgId = cursor.getString(1) ?: key.id,
                            text = cursor.getString(5) ?: "",
                            timestamp = cursor.getLong(6),
                            fromMe = fromMe,
                            isGroup = isGroup
                        )) enqueued++
                        recognized++
                    }
                }
            }
            if (enqueued < recognized) warnPreservationUnconfirmed()
            // Row recognition is neither the origin token nor a manager receipt.
            return recognized > 0
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Error copying selected messages: ${t.javaClass.simpleName}")
            return false
        }
    }

}
