package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.SharedPreferences
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.os.Bundle
import com.waenhancer.xposed.core.BaseFeature
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import org.luckypray.dexkit.query.FindMethod
import org.luckypray.dexkit.query.enums.StringMatchType
import org.luckypray.dexkit.query.matchers.MethodMatcher
import java.io.File
import java.lang.reflect.Method

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
        private const val PROVIDER_URI = "content://com.waenhancer.hookprovider"

        private val deleteForMeScope = ThreadLocal<Boolean>()

        /** Lets other database hooks distinguish a local Delete-for-me from a remote revoke. */
        @JvmStatic
        fun isDeleteForMeInProgress(): Boolean = deleteForMeScope.get() == true
    }

    override fun hook() {
        hookBytecodeDeleteForMe()
        hookDatabaseDeleteForMe()
    }

    private fun hookBytecodeDeleteForMe() {
        try {
            val deleteMethod = resolveDeleteForMeMethod()
            if (deleteMethod != null) {
                XposedBridge.log("$TAG Installed Delete for me hook: $deleteMethod")
                XposedBridge.hookMethod(
                    deleteMethod,
                    object : XC_MethodHook() {
                        override fun beforeHookedMethod(param: MethodHookParam) {
                            if (!isEnabled(PREF_KEY, false)) return
                            if (deleteMethod.name == "run" && !isDeleteForMeRunnable(param.thisObject)) return
                            deleteForMeScope.set(true)
                        }

                        override fun afterHookedMethod(param: MethodHookParam) {
                            deleteForMeScope.remove()
                        }
                    }
                )
            } else {
                XposedBridge.log("$TAG Warning: DeleteForMe method not found via dexkit.")
            }
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Failed to install bytecode DeleteForMe hook: ${t.javaClass.simpleName}")
        }
    }

    private fun hookDatabaseDeleteForMe() {
        try {
            XposedBridge.hookAllMethods(
                SQLiteDatabase::class.java,
                "delete",
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        if (!isEnabled(PREF_KEY, false)) return
                        if (!isDeleteForMeInProgress()) return

                        val table = param.args.getOrNull(0) as? String ?: return
                        if (table != "message") return

                        val where = param.args.getOrNull(1) as? String ?: return
                        val whereArgs = param.args.getOrNull(2) as? Array<*>

                        val db = param.thisObject as? SQLiteDatabase ?: return

                        try {
                            val sqlArgs = whereArgs?.map { it?.toString() ?: "" }?.toTypedArray() ?: emptyArray()
                            val querySql = "SELECT _id, key_id, chat_row_id, from_me, message_type, text_data, timestamp, sender_jid_row_id FROM message WHERE $where"

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

                                            dispatchToManagerApp(
                                                jid = chatJid,
                                                chatName = chatDisplayName,
                                                senderName = senderDisplayName,
                                                msgId = keyId,
                                                text = textData,
                                                timestamp = if (msgTs > 0) msgTs else now,
                                                fromMe = fromMe,
                                                isGroup = isGroup
                                            )
                                        }
                                    } while (cursor.moveToNext())
                                }
                            }
                        } catch (t: Throwable) {
                            XposedBridge.log("$TAG Error inspecting message before delete: ${t.javaClass.simpleName}")
                        }
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Error installing DB Delete-For-Me hook: ${t.javaClass.simpleName}")
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
        } catch (ignored: Throwable) {}
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
        } catch (ignored: Throwable) {}
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
        } catch (ignored: Throwable) {}

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
        } catch (ignored: Throwable) {}

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
        } catch (ignored: Throwable) {}

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
        } catch (ignored: Throwable) {}

        if (!resolvedPhoneUser.isNullOrBlank()) {
            return "+$resolvedPhoneUser"
        }

        return if (userPart.all { it.isDigit() } && userPart.length in 10..15) {
            "+$userPart"
        } else {
            userPart
        }
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
    ) {
        try {
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
            context.contentResolver.call(
                Uri.parse(PROVIDER_URI),
                "record_preserved_message",
                null,
                bundle
            )
        } catch (ignored: Throwable) {}
    }

    private fun resolveDeleteForMeMethod(): Method? {
        return try {
            DexSearchEngine.getInstance().findMethodWithCache(
                context,
                classLoader,
                "wpp_delete_for_me_method_v5",
                { bridge, loader ->
                    val data = bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "CoreMessageStore/deleteMessageForMe",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull() ?: bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "msgstore/delete-for-me",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull()
                    if (data != null) {
                        data.getMethodInstance(loader)
                    } else {
                        resolveCurrentDeleteForMeRunnable(bridge, loader)
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Exception while searching DeleteForMe method: ${t.javaClass.simpleName}")
            null
        }
    }

    /**
     * WhatsApp 2.26.41+ moved local deletion into a multiplexed Runnable. Resolve it from the
     * delete-dialog contract instead of relying on an obfuscated class or method name:
     * dialog builder -> Delete-for-me listener -> Runnable constructor -> run().
     */
    private fun resolveCurrentDeleteForMeRunnable(
        bridge: org.luckypray.dexkit.DexKitBridge,
        loader: ClassLoader
    ): Method? {
        val dialogMethod = bridge.findMethod(
            FindMethod.create().matcher(
                MethodMatcher.create().addUsingString(
                    "dialog/delete no messages",
                    StringMatchType.Equals
                )
            )
        ).singleOrNull() ?: return null

        val deleteListenerConstructor = dialogMethod.invokes.singleOrNull { invoked ->
            if (!invoked.isConstructor) return@singleOrNull false
            val params = invoked.paramTypeNames
            if (params.firstOrNull() != "android.widget.CheckBox" ||
                "java.util.Set" !in params) return@singleOrNull false
            val declaredClass = invoked.declaredClass ?: return@singleOrNull false
            declaredClass.interfaces.any {
                it.name == "android.content.DialogInterface\$OnClickListener"
            }
        } ?: return null

        val deleteListenerClass = deleteListenerConstructor.declaredClass ?: return null
        val onClick = deleteListenerClass.methods.singleOrNull { method ->
            method.name == "onClick" &&
                method.paramTypeNames == listOf("android.content.DialogInterface", "int") &&
                method.returnTypeName == "void"
        } ?: return null

        val deleteRunnableConstructor = onClick.invokes.singleOrNull { invoked ->
            if (!invoked.isConstructor || "int" !in invoked.paramTypeNames) {
                return@singleOrNull false
            }
            val declaredClass = invoked.declaredClass ?: return@singleOrNull false
            declaredClass.interfaces.any { it.name == "java.lang.Runnable" }
        } ?: return null

        val deleteRunnableClass = deleteRunnableConstructor.declaredClass ?: return null
        return deleteRunnableClass.methods.singleOrNull { method ->
            method.name == "run" && method.paramCount == 0 && method.returnTypeName == "void"
        }?.getMethodInstance(loader)
    }

    private fun isDeleteForMeRunnable(instance: Any?): Boolean {
        if (instance == null) return false
        return try {
            val discriminator = instance.javaClass.declaredFields.singleOrNull {
                it.type == Int::class.javaPrimitiveType
            } ?: return false
            discriminator.isAccessible = true
            // Reviewed in WhatsApp Business 2.26.41.3: case 6 is Delete for me.
            discriminator.getInt(instance) == 6
        } catch (_: Throwable) {
            false
        }
    }
}
