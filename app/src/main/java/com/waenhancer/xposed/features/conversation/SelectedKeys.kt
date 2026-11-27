package com.waenhancer.xposed.features.conversation

import java.lang.reflect.Field
import java.lang.reflect.Modifier

internal data class SelectedKey(val id: String, val chatJid: String, val fromMe: Boolean)

/** A reader for explicitly supplied semantic types, NOT a host key-class finder. A future host
 * binding must also establish the meaning of the JID projection (chat, not author/participant).
 * A two-key message needs an independently proven accessor, not this single-field contract. */
internal class SelectedKeys private constructor(private val message: Class<*>, private val own: Field,
    private val id: Field, private val direction: Field, private val chat: Field,
    private val rawJid: (Any) -> String?) {
    companion object {
        private fun fields(type: Class<*>) = generateSequence(type) { it.superclass }.takeWhile {
            it != Any::class.java
        }.flatMap { it.declaredFields.asSequence() }.filterNot { Modifier.isStatic(it.modifiers) }.toList()

        fun unique(message: Class<*>, key: Class<*>, jid: Class<*>, rawJid: (Any) -> String?): SelectedKeys? {
            val own = fields(message).singleOrNull { key.isAssignableFrom(it.type) } ?: return null
            val layout = fields(key)
            if (layout.size != 3 || own.type != key) return null
            val id = layout.singleOrNull { it.type == String::class.java } ?: return null
            val direction = layout.singleOrNull { it.type == Boolean::class.javaPrimitiveType } ?: return null
            val chat = layout.singleOrNull { it.type == jid } ?: return null
            if (chat == id || jid.isPrimitive) return null
            for (field in listOf(own, id, direction, chat)) field.isAccessible = true
            return SelectedKeys(message, own, id, direction, chat, rawJid)
        }
    }

    fun read(value: Any?): SelectedKey? {
        if (value?.javaClass != message) return null
        val key = own.get(value) ?: return null
        if (key.javaClass != own.type) return null
        val msgId = id.get(key) as? String ?: return null
        val raw = rawJid(chat.get(key) ?: return null) ?: return null
        if (raw.isBlank() || msgId.isBlank()) return null
        return SelectedKey(msgId, raw, direction.getBoolean(key))
    }
}
