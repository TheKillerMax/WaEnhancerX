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
import java.lang.reflect.Modifier

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
        private const val SCOPE_ENTERED = "waex_preserve_delete_scope_entered"
        private const val SCOPE_PREVIOUS = "waex_preserve_delete_scope_previous"

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
                            if (isDedicatedDeleteAction(deleteMethod)) {
                                // This local-delete action enqueues work. Capture the selected
                                // collection before that request; the thread scope is synchronous.
                                val selected = param.args.getOrNull(0) as? Collection<*> ?: return
                                if (!captureSelectedMessages(selected)) return
                            } else if (deleteMethod.name == "run") {
                                // Multiplexed Runnables are shared by unrelated WhatsApp features.
                                // Only enter the delete scope after resolving real message keys.
                                if (!captureRunnableMessages(param.thisObject)) return
                            }
                            param.setObjectExtra(SCOPE_PREVIOUS, deleteForMeScope.get() == true)
                            param.setObjectExtra(SCOPE_ENTERED, true)
                            deleteForMeScope.set(true)
                        }

                        override fun afterHookedMethod(param: MethodHookParam) {
                            if (param.getObjectExtra(SCOPE_ENTERED) != true) return
                            if (param.getObjectExtra(SCOPE_PREVIOUS) == true) deleteForMeScope.set(true)
                            else deleteForMeScope.remove()
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
                        if (!isTargetMessageStore(db)) return

                        try {
                            val sqlArgs = whereArgs?.map { it?.toString() ?: "" }?.toTypedArray() ?: emptyArray()
                            val querySql = "SELECT _id, key_id, chat_row_id, from_me, message_type, text_data, timestamp, sender_jid_row_id FROM message WHERE $where"

                            db.rawQuery(querySql, sqlArgs).use { cursor ->
                                if (cursor != null && cursor.moveToFirst()) {
                                    do {
                                        val keyId = cursor.getString(1)
                                        val chatRowId = cursor.getLong(2)
                                        val direction = cursor.getInt(3)
                                        if (direction !in 0..1) continue
                                        val fromMe = direction == 1
                                        val msgType = cursor.getInt(4)
                                        val textData = cursor.getString(5) ?: ""
                                        val msgTs = cursor.getLong(6)
                                        val senderJidRowId = if (cursor.columnCount > 7) cursor.getLong(7) else 0L

                                        if (!keyId.isNullOrEmpty() && msgType != 15) {
                                            val now = System.currentTimeMillis()
                                            val chatJid = resolveChatJid(db, chatRowId) ?: continue
                                            val isGroup = com.waenhancer.utils.ContactIdentityPolicy.isGroup(chatJid)
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

    private fun isTargetMessageStore(db: SQLiteDatabase): Boolean = try {
        File(db.path).canonicalFile == context.getDatabasePath("msgstore.db").canonicalFile
    } catch (_: Exception) {
        false
    }

    private fun resolveChatJid(db: SQLiteDatabase, chatRowId: Long): String? {
        if (chatRowId <= 0) return null
        try {
            val sql = "SELECT raw_string FROM jid WHERE _id = (SELECT jid_row_id FROM chat WHERE _id = ?)"
            db.rawQuery(sql, arrayOf(chatRowId.toString())).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    val raw = cursor.getString(0)
                    return com.waenhancer.utils.ContactIdentityPolicy.canonicalJid(raw)
                }
            }
        } catch (ignored: Throwable) {}
        return null
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
            msgstoreDb.rawQuery("SELECT raw_string FROM jid WHERE _id = ?", arrayOf(senderJidRowId.toString())).use { cursor ->
                if (cursor != null && cursor.moveToFirst()) {
                    rawJid = cursor.getString(0) ?: ""
                }
            }
            if (rawJid.isNotBlank()) {
                val resolved = resolveUserDisplayName(ctx, rawJid)
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

        return resolveUserDisplayName(ctx, rawJid)
    }

    private fun resolveUserDisplayName(
        ctx: Context,
        rawJid: String
    ): String {
        // Reuse the exact namespace-aware resolver. A numeric LID is not a phone number,
        // and suffix/substring matches can attach an unrelated person's name to a capture.
        return com.waenhancer.utils.ContactNameResolver.resolveName(ctx, rawJid, null, null)
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
        resolveDedicatedDeleteAction()?.let { return it }
        return try {
            DexSearchEngine.getInstance().findMethodWithCache(
                context,
                classLoader,
                "wpp_delete_for_me_legacy_method_v8",
                { bridge, loader ->
                    resolveCurrentDeleteForMeRunnable(bridge, loader) ?: bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "CoreMessageStore/deleteMessageForMe",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull()?.getMethodInstance(loader)?.takeIf {
                        it.name != "run" || it.parameterCount > 0
                    } ?: bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "msgstore/delete-for-me",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull()?.getMethodInstance(loader)?.takeIf {
                        it.name != "run" || it.parameterCount > 0
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Exception while searching DeleteForMe method: ${t.javaClass.simpleName}")
            null
        }
    }

    private fun isDedicatedDeleteAction(method: Method): Boolean =
        !Modifier.isStatic(method.modifiers) && method.returnType == Void.TYPE &&
            method.parameterTypes.contentEquals(arrayOf(
                Collection::class.java, Boolean::class.javaPrimitiveType, Boolean::class.javaPrimitiveType
            ))

    private fun resolveDedicatedDeleteAction(): Method? = try {
        DexSearchEngine.getInstance().findMethodWithCache(
            context, classLoader, "wpp_delete_for_me_collection_action_v8",
            { bridge, loader ->
                bridge.findMethod(FindMethod.create().matcher(
                    MethodMatcher.create()
                        .addUsingString("UserActionsMessageDeletion/userActionDeleteMessages ", StringMatchType.Equals)
                        .addUsingString("UserActionsMessageDeletion/userActionDeleteMessages messagesToDeleteIncludingAssociatedMessages=", StringMatchType.Equals)
                )).filter {
                    it.returnTypeName == "void" &&
                        it.paramTypeNames == listOf("java.util.Collection", "boolean", "boolean")
                }.mapNotNull {
                    try { it.getMethodInstance(loader).takeIf(::isDedicatedDeleteAction) }
                    catch (_: ReflectiveOperationException) { null }
                    catch (_: LinkageError) { null }
                }.singleOrNull()
            }
        )?.takeIf(::isDedicatedDeleteAction) // Recheck even when returned by the reflection cache.
    } catch (t: Throwable) {
        XposedBridge.log("$TAG Exception while searching local delete action: ${t.javaClass.simpleName}")
        null
    }

    /**
     * Resolve the local-delete Runnable from WhatsApp's stable semantic and interface graph rather
     * than obfuscated names, synthetic switch values, or constructor arity:
     * message-key helper string -> dialog builder(Set) -> positive listener -> Runnable -> run().
     */
    private fun resolveCurrentDeleteForMeRunnable(
        bridge: org.luckypray.dexkit.DexKitBridge,
        loader: ClassLoader
    ): Method? {
        val deleteDialogAnchors = bridge.findMethod(
            FindMethod.create().matcher(
                MethodMatcher.create().addUsingString(
                    "DeleteMessagesDialog/getSampleMessageForMediaType/multi chat jid delete",
                    StringMatchType.Equals
                )
            )
        )
        val deleteDialogAnchor = deleteDialogAnchors.firstOrNull() ?: return null

        val dialogBuilders = deleteDialogAnchor.declaredClass?.methods?.filter { method ->
            val params = method.paramTypeNames
            "java.util.Set" in params && "boolean" in params && params.size >= 6
        }.orEmpty()
        val dialogBuilder = dialogBuilders.firstOrNull() ?: return null

        val deleteListenerConstructor = dialogBuilder.invokes.firstOrNull { invoked ->
            if (!invoked.isConstructor) return@firstOrNull false
            val params = invoked.paramTypeNames
            if (params.firstOrNull() != "android.widget.CheckBox" ||
                "java.util.Set" !in params) return@firstOrNull false
            val declaredClass = invoked.declaredClass ?: return@firstOrNull false
            declaredClass.interfaces.any {
                it.name == "android.content.DialogInterface\$OnClickListener"
            }
        } ?: return null

        val deleteListenerClass = deleteListenerConstructor.declaredClass ?: return null
        val onClick = deleteListenerClass.methods.firstOrNull { method ->
            method.name == "onClick" &&
                method.paramTypeNames == listOf("android.content.DialogInterface", "int") &&
                method.returnTypeName == "void"
        } ?: return null

        val deleteRunnableConstructor = onClick.invokes.firstOrNull { invoked ->
            if (!invoked.isConstructor) return@firstOrNull false
            val params = invoked.paramTypeNames
            if ("int" !in params || "boolean" !in params) return@firstOrNull false
            val declaredClass = invoked.declaredClass ?: return@firstOrNull false
            declaredClass.interfaces.any { it.name == "java.lang.Runnable" }
        } ?: return null

        val deleteRunnableClass = deleteRunnableConstructor.declaredClass ?: return null
        return deleteRunnableClass.methods.firstOrNull { method ->
            method.name == "run" && method.paramCount == 0 && method.returnTypeName == "void"
        }?.getMethodInstance(loader)
    }

    /**
     * Current WhatsApp versions delete through an internal message-store API and may never call
     * SQLiteDatabase.delete(). The Delete-for-me Runnable still owns the selected message Set, so
     * copy those rows to the WAEX vault before allowing the Runnable to continue.
     */
    private fun captureRunnableMessages(instance: Any?): Boolean {
        if (instance == null) return false
        try {
            val messageSets = generateSequence(instance.javaClass as Class<*>?) { it.superclass }
                .takeWhile { it != Any::class.java }
                .flatMap { it.declaredFields.asSequence() }
                .filterNot { it.type.isPrimitive || Modifier.isStatic(it.modifiers) }
                .mapNotNull { field ->
                    field.isAccessible = true
                    field.get(instance) as? Set<*>
                }
                .toList()
            if (messageSets.isEmpty()) return false

            return captureSelectedMessages(messageSets.flatMap { it })
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Error reading selected message collection: ${t.javaClass.simpleName}")
            return false
        }
    }

    private fun captureSelectedMessages(messages: Collection<*>): Boolean {
        try {
            val keys = messages.asSequence()
                .mapNotNull(PreservedMessageSelection::read).distinct().toList()
            if (keys.isEmpty()) {
                XposedBridge.log("$TAG Warning: selected message keys were not resolved")
                return false
            }

            val dbFile = context.getDatabasePath("msgstore.db")
            if (!dbFile.exists()) {
                XposedBridge.log("$TAG Warning: msgstore.db was not found")
                return false
            }

            var captured = 0
            SQLiteDatabase.openDatabase(dbFile.absolutePath, null, SQLiteDatabase.OPEN_READONLY).use { db ->
                keys.forEach { key ->
                    db.rawQuery(
                        PreservedMessageSelection.QUERY,
                        key.queryArgs()
                    ).use { cursor ->
                        if (!cursor.moveToFirst() || cursor.getInt(4) == 15) return@use
                        // Two physical rows for the same full key are ambiguous. Do not pick one.
                        if (cursor.moveToNext()) return@use
                        if (!cursor.moveToFirst()) return@use
                        val chatRowId = cursor.getLong(2)
                        val fromMe = cursor.getInt(3) == 1
                        val chatJid = cursor.getString(8) ?: return@use
                        if (cursor.getString(1) != key.id || chatJid != key.chatJid || fromMe != key.fromMe) return@use
                        val isGroup = com.waenhancer.utils.ContactIdentityPolicy.isGroup(chatJid)
                        val chatName = resolveChatDisplayName(context, db, chatRowId, chatJid)
                        val senderName = if (isGroup) {
                            resolveSenderDisplayName(context, db, cursor.getLong(7), chatName)
                        } else if (fromMe) {
                            "You"
                        } else {
                            chatName
                        }
                        dispatchToManagerApp(
                            jid = chatJid,
                            chatName = chatName,
                            senderName = senderName,
                            msgId = cursor.getString(1) ?: key.id,
                            text = cursor.getString(5) ?: "",
                            timestamp = cursor.getLong(6),
                            fromMe = fromMe,
                            isGroup = isGroup
                        )
                        captured++
                    }
                }
            }
            // The existing provider response is not a persisted-write acknowledgement.
            XposedBridge.log("$TAG Prepared $captured Delete for me capture request(s)")
            return captured > 0
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Error copying selected messages: ${t.javaClass.simpleName}")
            return false
        }
    }

}
