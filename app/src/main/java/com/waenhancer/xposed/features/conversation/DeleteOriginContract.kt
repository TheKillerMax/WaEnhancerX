package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.DialogInterface
import android.widget.CheckBox
import org.luckypray.dexkit.DexKitBridge
import org.luckypray.dexkit.query.FindMethod
import org.luckypray.dexkit.query.enums.StringMatchType
import org.luckypray.dexkit.query.matchers.MethodMatcher
import org.luckypray.dexkit.result.FieldUsingType
import org.luckypray.dexkit.result.MethodData
import java.lang.reflect.Constructor
import java.lang.reflect.Field
import java.lang.reflect.Member
import java.lang.reflect.Method
import java.lang.reflect.Modifier

/** Facts, not decisions. Tests substitute an instruction index, not a preselected run method. */
internal interface DeleteCode {
    fun tagged(exact: Boolean, vararg strings: String): List<Member>
    fun invokes(method: Method): List<Member>
    fun callers(ctor: Constructor<*>): Set<Member>
    fun fields(member: Member, write: Boolean): Set<Field>
}

internal class DexDeleteCode(private val dex: DexKitBridge, private val loader: ClassLoader) : DeleteCode {
    private fun member(m: MethodData): Member = if (m.isConstructor) m.getConstructorInstance(loader)
        else m.getMethodInstance(loader)

    override fun tagged(exact: Boolean, vararg strings: String): List<Member> {
        val matcher = MethodMatcher.create()
        val mode = if (exact) StringMatchType.Equals else StringMatchType.Contains
        for (text in strings) matcher.addUsingString(text, mode)
        return dex.findMethod(FindMethod.create().matcher(matcher)).map(::member)
    }

    private fun data(m: Member): MethodData = checkNotNull(when (m) {
        is Method -> dex.getMethodData(m)
        is Constructor<*> -> dex.getMethodData(m)
        else -> null
    })
    override fun invokes(method: Method) = data(method).invokes.map(::member)
    override fun callers(ctor: Constructor<*>) = data(ctor).callers.map(::member).toSet()
    override fun fields(member: Member, write: Boolean) = data(member).usingFields.filter {
        it.usingType == (if (write) FieldUsingType.Write else FieldUsingType.Read)
    }.map { it.field.getFieldInstance(loader) }.toSet()
}

internal sealed class DeleteRoute {
    class Store(val method: Method) : DeleteRoute()
    class Local(val builder: Method, val listener: Constructor<*>, val click: Method,
                val owner: Field, val selection: Field, val construct: Constructor<*>,
                val carried: List<Field>, val run: Method, val api: Method) : DeleteRoute()

    companion object {
        private val int = Integer.TYPE
        private val bool = Boolean::class.javaPrimitiveType!!
        private val boxed = Int::class.javaObjectType
        private fun usable(m: Method) = !Modifier.isAbstract(m.modifiers) && !Modifier.isNative(m.modifiers)
        private fun singleBody(c: Class<*>, name: String, vararg args: Class<*>): Method? =
            c.declaredMethods.singleOrNull { it.name == name }?.takeIf {
                it.parameterTypes.toList() == args.toList() && it.returnType == Void.TYPE &&
                    !Modifier.isStatic(it.modifiers) && usable(it)
            }

        fun resolve(code: DeleteCode, personal: Boolean): DeleteRoute? {
            val builders = code.tagged(true, "dialog/delete no messages", "pref_delete_media")
            if (builders.isEmpty()) {
                // Only the historical, semantically anchored store entry can use the SQL path.
                val entries = code.tagged(false, "CoreMessageStore/deleteMessageForMe") +
                    code.tagged(false, "msgstore/delete-for-me")
                val m = entries.distinct().singleOrNull() as? Method ?: return null
                return if (m.name != "run" && usable(m)) Store(m) else null
            }
            if (!personal) return null
            val b = builders.singleOrNull() as? Method ?: return null
            val p = b.parameterTypes.toList()
            if (!usable(b) || b.returnType.isPrimitive || p.size != 8 || p[0] != Context::class.java ||
                p.subList(1, 4).any { it.isPrimitive } ||
                p.drop(4) != listOf(String::class.java, Set::class.java, int, bool)) return null
            val listenerArgs = listOf(CheckBox::class.java) + p.subList(1, 4) +
                listOf(b.declaringClass, boxed, Set::class.java, bool, bool)
            val listener = code.invokes(b).filterIsInstance<Constructor<*>>().distinct().singleOrNull {
                DialogInterface.OnClickListener::class.java in it.declaringClass.interfaces &&
                    it.parameterTypes.toList() == listenerArgs
            } ?: return null
            val lc = listener.declaringClass
            if (lc.superclass != Any::class.java || lc.declaredConstructors.singleOrNull() != listener ||
                code.callers(listener) != setOf(b)) return null
            val click = singleBody(lc, "onClick", DialogInterface::class.java, int) ?: return null
            val fields = lc.declaredFields.filterNot { Modifier.isStatic(it.modifiers) }
            val owner = fields.singleOrNull { it.type == b.declaringClass } ?: return null
            val selection = fields.singleOrNull { it.type == Set::class.java } ?: return null
            val passed = code.fields(listener, true) intersect code.fields(click, false)
            if (owner !in passed || selection !in passed) return null
            val ctor = code.invokes(click).filterIsInstance<Constructor<*>>().distinct().singleOrNull {
                Runnable::class.java in it.declaringClass.interfaces
            } ?: return null
            val jc = ctor.declaringClass
            if (jc.superclass != Any::class.java || jc.declaredConstructors.singleOrNull() != ctor ||
                ctor.parameterTypes.toList() != List(5) { Any::class.java } + listOf(int, bool, bool)) return null
            val run = singleBody(jc, "run") ?: return null
            val carried = (code.fields(ctor, true) intersect code.fields(run, false)).filter {
                it.declaringClass == jc && !Modifier.isStatic(it.modifiers) && it.type == Any::class.java
            }
            if (carried.size < 2) return null
            val taggedApis = code.tagged(true, "UserActionsMessageDeletion/userActionDeleteMessages ")
            val api = code.invokes(run).distinct().filterIsInstance<Method>().singleOrNull {
                it in taggedApis && usable(it) && it.returnType == Void.TYPE &&
                    it.parameterTypes.toList() == listOf(boxed, Collection::class.java, bool, bool)
            } ?: return null
            for (f in carried + listOf(owner, selection)) f.isAccessible = true
            return Local(b, listener, click, owner, selection, ctor, carried, run, api)
        }
    }
}
