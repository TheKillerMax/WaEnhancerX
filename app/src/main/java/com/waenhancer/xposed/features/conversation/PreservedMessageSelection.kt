package com.waenhancer.xposed.features.conversation

import com.waenhancer.utils.ContactIdentityPolicy
import java.lang.reflect.Modifier

/** A local message key is the chat, direction and ID together. */
internal data class PreservedMessageSelection(
    val id: String,
    val chatJid: String,
    val fromMe: Boolean
) {
    fun queryArgs(): Array<String> = arrayOf(id, if (fromMe) "1" else "0", chatJid)

    companion object {
        const val QUERY = "SELECT m._id, m.key_id, m.chat_row_id, m.from_me, " +
            "m.message_type, m.text_data, m.timestamp, m.sender_jid_row_id, j.raw_string " +
            "FROM message m JOIN chat c ON c._id = m.chat_row_id " +
            "JOIN jid j ON j._id = c.jid_row_id " +
            "WHERE m.key_id = ? AND m.from_me = ? AND j.raw_string = ? LIMIT 2"

        /**
         * Current FMessage keys contain an instance String, primitive boolean and host Jid.
         * Accept the key itself or one unambiguous message-owned key. Static metadata,
         * arbitrary objects with a JID-like toString(), and conflicting keys are not evidence.
         */
        fun read(message: Any?): PreservedMessageSelection? {
            if (message == null) return null
            return try {
                readKey(message)?.let { return it }
                val candidates = mutableSetOf<PreservedMessageSelection>()
                for (field in instanceFields(message.javaClass)) {
                    if (!isKeyType(field.type)) continue
                    field.isAccessible = true
                    readKey(field.get(message))?.let(candidates::add)
                }
                // Older hosts expose the same typed key through this accessor.
                for (method in message.javaClass.methods) {
                    if (method.name != "Atl" || method.parameterTypes.size != 0 ||
                        Modifier.isStatic(method.modifiers) || !isKeyType(method.returnType)) continue
                    readKey(method.invoke(message))?.let(candidates::add)
                }
                candidates.singleOrNull()
            } catch (_: ReflectiveOperationException) {
                null
            } catch (_: RuntimeException) {
                null
            } catch (_: LinkageError) {
                null
            }
        }

        private fun readKey(key: Any?): PreservedMessageSelection? {
            if (key == null || !isKeyType(key.javaClass)) return null
            val fields = instanceFields(key.javaClass).toList()
            val idField = fields.single { it.type == String::class.java }
            val fromMeField = fields.single { it.type == Boolean::class.javaPrimitiveType }
            val jidField = fields.single { isJidType(it.type) }
            idField.isAccessible = true
            fromMeField.isAccessible = true
            jidField.isAccessible = true
            val id = idField.get(key) as? String ?: return null
            if (id.isBlank()) return null
            val jid = ContactIdentityPolicy.canonicalJid(jidField.get(key)?.toString()) ?: return null
            return PreservedMessageSelection(id, jid, fromMeField.getBoolean(key))
        }

        private fun isKeyType(type: Class<*>): Boolean {
            if (type.isPrimitive || type == String::class.java || type.isArray) return false
            val fields = instanceFields(type).toList()
            return fields.size == 3 &&
                fields.count { it.type == String::class.java } == 1 &&
                fields.count { it.type == Boolean::class.javaPrimitiveType } == 1 &&
                fields.count { isJidType(it.type) } == 1
        }

        private fun isJidType(type: Class<*>): Boolean {
            var current: Class<*>? = type
            while (current != null) {
                if (current.name == "com.whatsapp.infra.core.jid.Jid" ||
                    current.name == "com.whatsapp.jid.Jid") return true
                current = current.superclass
            }
            return false
        }

        private fun instanceFields(type: Class<*>): Sequence<java.lang.reflect.Field> = sequence {
            var current: Class<*>? = type
            while (current != null && current != Any::class.java) {
                yieldAll(current.declaredFields.asSequence().filterNot { Modifier.isStatic(it.modifiers) })
                current = current.superclass
            }
        }
    }
}
