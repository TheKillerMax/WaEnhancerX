#!/usr/bin/env python3
"""Compile the complete forwarding hook against explicit Android/Xposed/DexKit doubles.

The synthetic numeric method performs a flags OR. The old selector resolves it
even when no forwarding caller is found, reproducing the unsafe contract without
including host bytecode. No WhatsApp transport or visual behavior is certified.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/com/waenhancer/xposed/features/privacy/HideForwardedTagHook.kt'

STUBS = {
    'Android.kt': '''package android.content
open class Context
interface SharedPreferences {
    fun contains(key: String): Boolean
    fun getBoolean(key: String, fallback: Boolean): Boolean
}
class ContentValues {
    val values = mutableMapOf<String, Any?>()
    constructor()
    constructor(other: ContentValues) { values.putAll(other.values) }
    fun put(key: String, value: Int) { values[key] = value }
    fun get(key: String): Any? = values[key]
}
''',
    'Db.kt': 'package android.database.sqlite\nclass SQLiteDatabase\n',
    'Base.kt': '''package com.waenhancer.xposed.core
import android.content.*
abstract class BaseFeature(val context: Context, val classLoader: ClassLoader,
                           val prefs: SharedPreferences) {
    abstract val name: String
    abstract fun hook()
}
''',
    'Host.kt': '''package fixture
// A synthetic counterexample, not decompiled or copied host code.
class FlagsMessage {
    var flags: Long = 4L
    fun addFlags(bits: Long) { flags = flags or bits }
}
''',
    'Xposed.kt': '''package de.robv.android.xposed
import java.lang.reflect.Method
open class XC_MethodHook {
    class MethodHookParam(val args: Array<Any?>)
    protected open fun beforeHookedMethod(param: MethodHookParam) {}
    fun invoke(param: MethodHookParam) { beforeHookedMethod(param) }
}
object XposedBridge {
    val methodHooks = mutableListOf<Pair<Method, XC_MethodHook>>()
    fun log(message: String) {}
    fun hookMethod(method: Method, hook: XC_MethodHook) { methodHooks.add(method to hook) }
}
object XposedHelpers {
    val hooks = mutableListOf<Pair<String, XC_MethodHook>>()
    fun findAndHookMethod(type: Class<*>, name: String, vararg args: Any?) {
        check(type.name == "android.database.sqlite.SQLiteDatabase")
        hooks.add(name to (args.last() as XC_MethodHook))
    }
}
''',
    'Enums.kt': 'package org.luckypray.dexkit.query.enums\nenum class StringMatchType { Contains }\n',
    'Matchers.kt': '''package org.luckypray.dexkit.query.matchers
import org.luckypray.dexkit.query.enums.StringMatchType
class ClassMatcher {
    var anchor = ""
    fun addUsingString(value: String, kind: StringMatchType): ClassMatcher { anchor = value; return this }
    companion object { fun create() = ClassMatcher() }
}
class MethodMatcher {
    var anchor = ""
    fun addUsingString(value: String, kind: StringMatchType): MethodMatcher { anchor = value; return this }
    companion object { fun create() = MethodMatcher() }
}
''',
    'Queries.kt': '''package org.luckypray.dexkit.query
import org.luckypray.dexkit.query.matchers.*
class FindClass {
    lateinit var queryMatcher: ClassMatcher
    fun matcher(value: ClassMatcher): FindClass { queryMatcher = value; return this }
    companion object { fun create() = FindClass() }
}
class FindMethod {
    lateinit var queryMatcher: MethodMatcher
    fun matcher(value: MethodMatcher): FindMethod { queryMatcher = value; return this }
    companion object { fun create() = FindMethod() }
}
''',
    'Dex.kt': '''package com.waenhancer.xposed.core.devkit
import android.content.Context
import java.lang.reflect.Method
import org.luckypray.dexkit.query.*
object ResolverEvidence { var emptyCallerResults = 0; var numericSelections = 0 }
class ClassMatch { fun getInstance(loader: ClassLoader): Class<*> = fixture.FlagsMessage::class.java }
class Invocation {
    fun getMethodInstance(loader: ClassLoader): Method {
        ResolverEvidence.numericSelections++
        return fixture.FlagsMessage::class.java.getDeclaredMethod("addFlags", Long::class.javaPrimitiveType)
    }
}
class MethodMatch { val invokes = listOf(Invocation()) }
class FakeBridge {
    fun findClass(query: FindClass): List<ClassMatch> {
        if (query.queryMatcher.anchor == "FMessage/getSenderUserJid/key.id") return listOf(ClassMatch())
        ResolverEvidence.emptyCallerResults++
        return emptyList()
    }
    fun findMethod(query: FindMethod): List<MethodMatch> =
        if (query.queryMatcher.anchor == "chatInfo/incrementUnseenImportantMessageCount") listOf(MethodMatch())
        else emptyList()
}
class DexSearchEngine {
    val bridge: FakeBridge? = FakeBridge()
    companion object { fun getInstance() = DexSearchEngine() }
}
class DexCacheManager {
    fun getClass(loader: ClassLoader, key: String, resolve: () -> Class<*>?): Class<*>? = resolve()
    fun getMethod(loader: ClassLoader, key: String, resolve: () -> Method?): Method? = resolve()
    companion object { fun getInstance(context: Context) = DexCacheManager() }
}
''',
    'Test.kt': '''package com.waenhancer.xposed.features.privacy
import android.content.*
import de.robv.android.xposed.*
import com.waenhancer.xposed.core.devkit.ResolverEvidence
class Prefs : SharedPreferences {
    val values = mutableMapOf<String, Any?>()
    var failRead = false
    override fun contains(key: String): Boolean {
        if (failRead) throw IllegalStateException("unavailable")
        return values.containsKey(key)
    }
    override fun getBoolean(key: String, fallback: Boolean): Boolean =
        if (!contains(key)) fallback else values[key] as Boolean
}
fun main() {
    val prefs = Prefs()
    prefs.values["hide_forwarded_tag"] = true
    HideForwardedTagHook(Context(), Prefs::class.java.classLoader, prefs).hook()
    var checks = 0
    fun verify(label: String, value: Boolean) {
        if (!value) throw AssertionError("ASSERTION|" + label)
        checks++
    }

    // Exercise the actual hook registration and synthetic host invocation. The
    // original selector finds addFlags(long) while both caller lookups are empty.
    val host = fixture.FlagsMessage()
    val invocation = XC_MethodHook.MethodHookParam(arrayOf(8L))
    for ((_, hook) in XposedBridge.methodHooks) hook.invoke(invocation)
    host.addFlags(invocation.args[0] as Long)
    println("COUNTEREXAMPLE: numeric selections=${ResolverEvidence.numericSelections}, " +
        "empty caller results=${ResolverEvidence.emptyCallerResults}, flags=${host.flags}")
    verify("numeric flags OR must preserve all requested bits even with no caller anchor", host.flags == 12L)
    verify("no ambiguous numeric method interception", XposedBridge.methodHooks.isEmpty())
    verify("only supported database callbacks", XposedHelpers.hooks.map { it.first } ==
        listOf("insertWithOnConflict", "insert", "insertOrThrow"))

    for ((name, hook) in XposedHelpers.hooks) {
        fun insert(table: Any?, score: Any?, present: Boolean = true,
                   origin: Any? = 9, originPresent: Boolean = true): ContentValues {
            val original = ContentValues()
            if (present) original.values["forward_score"] = score
            if (originPresent) original.values["forward_origin"] = origin
            original.values["transport_flags"] = 33554432L
            original.values["unrelated"] = "retained"
            val snapshot = original.values.toMap()
            val args = XC_MethodHook.MethodHookParam(arrayOf(table, null, original, 0))
            hook.invoke(args)
            val inserted = args.args[2] as ContentValues
            verify("caller ContentValues unchanged $name", original.values == snapshot)
            verify("origin presence unchanged $name", inserted.values.containsKey("forward_origin") == originPresent)
            verify("origin value unchanged $name", inserted.values["forward_origin"] == origin)
            verify("transport flags unchanged $name", inserted.values["transport_flags"] == 33554432L)
            verify("unrelated values unchanged $name", inserted.values["unrelated"] == "retained")
            verify("no columns added $name", inserted.values.keys == snapshot.keys)
            return inserted
        }
        prefs.values.clear()
        verify("disabled $name", insert("message_forwarded", 2).values["forward_score"] == 2)
        prefs.values["hidetag"] = true
        verify("legacy opt-in $name", insert("message_forwarded", 2).values["forward_score"] == 0)
        prefs.values["hide_forwarded_tag"] = false
        verify("explicit canonical disable wins $name", insert("message_forwarded", 2).values["forward_score"] == 2)
        prefs.values["hide_forwarded_tag"] = true
        verify("canonical enable $name", insert("message_forwarded", 2).values["forward_score"] == 0)
        verify("maximum positive score $name", insert("message_forwarded", Int.MAX_VALUE).values["forward_score"] == 0)
        for (table in listOf(null, "message", "message_forwarded_shadow", "Message_forwarded", 3)) {
            verify("exact table only $name", insert(table, 2).values["forward_score"] == 2)
        }
        verify("absent score $name", !insert("message_forwarded", null, false).values.containsKey("forward_score"))
        for (score in listOf<Any?>(null, "2", 2L, 2f, 0, -1)) {
            verify("unsupported or nonpositive score $name", insert("message_forwarded", score).values["forward_score"] == score)
        }
        for (origin in listOf<Any?>(null, "kept", 7L, byteArrayOf(1, 2))) {
            verify("arbitrary origin retained $name", insert("message_forwarded", 1, origin = origin).values["forward_score"] == 0)
        }
        verify("absent origin remains absent $name",
            !insert("message_forwarded", 1, origin = null, originPresent = false).values.containsKey("forward_origin"))
        prefs.values["hide_forwarded_tag"] = "true"
        verify("corrupt canonical setting fails closed $name", insert("message_forwarded", 2).values["forward_score"] == 2)
        prefs.values.remove("hide_forwarded_tag")
        prefs.values["hidetag"] = "true"
        verify("corrupt legacy setting fails closed $name", insert("message_forwarded", 2).values["forward_score"] == 2)
        prefs.failRead = true
        verify("unavailable settings fail closed $name", insert("message_forwarded", 2).values["forward_score"] == 2)
        prefs.failRead = false
        prefs.values["hide_forwarded_tag"] = true
        for (args in listOf(emptyArray<Any?>(), arrayOf<Any?>("message_forwarded"),
                            arrayOf<Any?>("message_forwarded", null, null), arrayOf<Any?>("message_forwarded", null, "wrong"))) {
            hook.invoke(XC_MethodHook.MethodHookParam(args))
            verify("incomplete callbacks harmless $name", true)
        }
    }
    println("PASS: $checks compiled forwarding contracts; explicit doubles, no Android/WhatsApp runtime claim")
}
''',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE,
                        help='Compile this complete hook for a baseline or negative control')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='waex-forward-') as directory:
        out = Path(directory)
        for name, contents in STUBS.items():
            (out / name).write_text(contents, encoding='utf-8')
        subprocess.run(['kotlinc', '-jvm-target', '17', str(args.source),
                        *map(str, out.glob('*.kt')), '-include-runtime', '-d', str(out / 'test.jar')],
                       check=True, timeout=90)
        print('COMPILE_OK: complete production hook with explicit Android/Xposed/DexKit doubles', flush=True)
        subprocess.run(['java', '-jar', str(out / 'test.jar')], check=True, timeout=45)


if __name__ == '__main__':
    main()
