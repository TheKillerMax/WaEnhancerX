#!/usr/bin/env python3
"""Compile the entire bubble-color hook; check reflective members and callbacks.

Android, DexKit lookup/cache and Xposed registration are explicit fixture boundaries.
The bytecode check is pre-D8/R8, not a proof of API-24 APK linkage or real host binding.
No actual WhatsApp classes, private settings or network are involved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('app/src/main/java/com/waenhancer/xposed/features/conversation/ChatBubbleColorsHook.kt')
PREFIX = 'com/waenhancer/xposed/features/conversation/ChatBubbleColorsHook'

STUBS = {
    'AndroidContent.kt': '''package android.content
open class Context
class SharedPreferences(val values: Map<String, Any>)
''',
    'Graphics.kt': '''package android.graphics
class Rect
object PorterDuff { enum class Mode { SRC_IN } }
data class PorterDuffColorFilter(val color: Int, val mode: PorterDuff.Mode)
''',
    'Drawable.kt': '''package android.graphics.drawable
import android.graphics.PorterDuffColorFilter
class Drawable { var colorFilter: PorterDuffColorFilter? = null }
''',
    'BaseFeature.kt': '''package com.waenhancer.xposed.core
import android.content.Context
import android.content.SharedPreferences
abstract class BaseFeature(protected val context: Context,
                           protected val classLoader: ClassLoader,
                           private val prefs: SharedPreferences) {
    abstract val name: String
    abstract fun hook()
    protected fun isEnabled(key: String, fallback: Boolean) =
        (prefs.values[key] as? Boolean) ?: fallback
    protected fun getIntPref(key: String, fallback: Int) =
        if (prefs.values.containsKey(key)) prefs.values.getValue(key) as Int else fallback
}
''',
    'Matcher.kt': '''package org.luckypray.dexkit.query.matchers
class MethodMatcher {
    var guard: String? = null
    fun addUsingString(value: String) = apply { guard = value }
    companion object { fun create() = MethodMatcher() }
}
''',
    'FindMethod.kt': '''package org.luckypray.dexkit.query
import org.luckypray.dexkit.query.matchers.MethodMatcher
class FindMethod {
    var constraint: MethodMatcher? = null
    fun matcher(value: MethodMatcher) = apply { constraint = value }
    companion object { fun create() = FindMethod() }
}
''',
    'DexSearchEngine.kt': '''package com.waenhancer.xposed.core.devkit
import android.content.Context
import java.lang.reflect.Method
import org.luckypray.dexkit.query.FindMethod
class MethodData(private val value: Method?) {
    fun getMethodInstance(loader: ClassLoader): Method = value ?: error("fixture unresolved method")
}
class Bridge {
    fun findMethod(query: FindMethod): List<MethodData> {
        check(query.constraint?.guard == "Unreachable code: direction=")
        return DexSearchEngine.methods.map(::MethodData)
    }
}
object DexSearchEngine {
    var methods = emptyList<Method?>()
    var queries = 0
    fun getInstance() = this
    fun findMethodsWithCache(context: Context, loader: ClassLoader, key: String,
                             lookup: (Bridge, ClassLoader) -> Array<Method>?): Array<Method>? {
        check(key == "waex_bubble_layer_factories_v2")
        queries++
        return lookup(Bridge(), loader)
    }
}
''',
    'Xposed.kt': '''package de.robv.android.xposed
import java.lang.reflect.Method
abstract class XC_MethodHook {
    class MethodHookParam(val method: Method, val args: Array<Any?>, val result: Any?)
    protected abstract fun afterHookedMethod(param: MethodHookParam)
    fun invoke(method: Method, args: Array<Any?>, result: Any?) =
        afterHookedMethod(MethodHookParam(method, args, result))
}
object XposedBridge {
    val registered = linkedMapOf<Method, XC_MethodHook>()
    val logs = mutableListOf<String>()
    fun hookMethod(method: Method, callback: XC_MethodHook) {
        check(registered.put(method, callback) == null) { "duplicate registration" }
    }
    fun log(line: String) { logs.add(line) }
}
''',
}

DRIVER = '''package fixture
import android.content.Context
import android.content.SharedPreferences
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.Rect
import android.graphics.drawable.Drawable
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import com.waenhancer.xposed.features.conversation.ChatBubbleColorsHook
import de.robv.android.xposed.XposedBridge
import java.lang.reflect.Method

abstract class Factories {
    fun body(direction: Int) = Drawable()
    fun padding(direction: Int) = Rect()
    fun wrapper(direction: Int, footer: Boolean) = Drawable()
    fun border(other: Int, direction: Int, footer: Boolean) = Drawable()
    fun wrongFirst(direction: String) = Drawable()
    abstract fun abstractLayer(direction: Int): Drawable
}

fun main() {
    val all = Factories::class.java.declaredMethods.associateBy { it.name }
    val body = all.getValue("body")
    val wrapper = all.getValue("wrapper")
    val border = all.getValue("border")
    val padding = all.getValue("padding")
    val expected = setOf(body, wrapper, border)
    val incoming = 0x112233
    val outgoing = 0x445566
    val oldFilter = PorterDuffColorFilter(0x778899, PorterDuff.Mode.SRC_IN)
    var checks = 0
    fun expect(label: String, condition: Boolean) {
        checks++
        if (!condition) throw AssertionError("BUBBLE_ASSERT|" + label)
    }
    fun start(values: Map<String, Any>, methods: List<Method?> = listOf(null, body, padding)) {
        XposedBridge.registered.clear()
        XposedBridge.logs.clear()
        DexSearchEngine.methods = methods
        DexSearchEngine.queries = 0
        ChatBubbleColorsHook(Context(), Factories::class.java.classLoader,
                             SharedPreferences(values)).hook()
    }
    fun tint(label: String, method: Method, args: Array<Any?>, color: Int?) {
        val drawable = Drawable()
        drawable.colorFilter = oldFilter
        XposedBridge.registered.getValue(method).invoke(method, args, drawable)
        expect(label, drawable.colorFilter == if (color == null) oldFilter else
            PorterDuffColorFilter(color, PorterDuff.Mode.SRC_IN))
    }
    val palette = mapOf<String, Any>("bubble_color" to true,
                                     "bubble_left" to incoming, "bubble_right" to outgoing)
    start(palette)
    expect("one_lookup", DexSearchEngine.queries == 1)
    expect("three_factories", XposedBridge.registered.keys == expected)
    expect("shared_callback", XposedBridge.registered.values.toSet().size == 1)
    tint("body_incoming", body, arrayOf(1), incoming)
    tint("body_outgoing", body, arrayOf(3), outgoing)
    tint("wrapper_incoming", wrapper, arrayOf(2, false), incoming)
    tint("wrapper_outgoing", wrapper, arrayOf(3, true), outgoing)
    tint("border_uses_second_outgoing", border, arrayOf(1, 3, true), outgoing)
    tint("border_uses_second_incoming", border, arrayOf(3, 1, true), incoming)
    tint("missing_direction", body, emptyArray(), null)
    tint("wrong_direction_type", body, arrayOf("3"), null)
    tint("missing_border_direction", border, arrayOf(3), null)
    XposedBridge.registered.getValue(body).invoke(body, arrayOf(3), "not a drawable")
    expect("non_drawable_ignored", XposedBridge.registered.keys == expected)
    start(palette + ("bubble_right" to 0))
    tint("zero_color_preserves_drawable", body, arrayOf(3), null)
    tint("other_color_still_applies", body, arrayOf(1), incoming)
    start(palette + ("bubble_right" to "bad type"))
    tint("wrong_color_type_preserves_drawable", body, arrayOf(3), null)
    start(palette + ("bubble_color" to false))
    expect("disabled_no_lookup", DexSearchEngine.queries == 0 && XposedBridge.registered.isEmpty())
    start(palette + ("bubble_left" to 0) + ("bubble_right" to 0))
    expect("empty_palette_no_lookup", DexSearchEngine.queries == 0 && XposedBridge.registered.isEmpty())
    start(palette + ("bubble_color" to false) + ("bubble_colors" to true))
    expect("legacy_enable_alias", XposedBridge.registered.keys == expected)
    start(palette, emptyList())
    expect("no_match_no_registration", DexSearchEngine.queries == 1 && XposedBridge.registered.isEmpty())
    start(palette, listOf(body))
    expect("body_only", XposedBridge.registered.keys == setOf(body))
    println("BUBBLE_BEHAVIOR_PASS checks=" + checks)
}
'''
EXPECTED_CHECKS = 21


def run_case(source, work):
    work.mkdir()
    for name, content in {**STUBS, 'Driver.kt': DRIVER}.items():
        (work / name).write_text(content, encoding='utf-8')
    (work / SOURCE.name).write_bytes(source)
    jar = work / 'checks.jar'
    compiler = shutil.which('kotlinc') or 'kotlinc'
    subprocess.run([compiler, '-nowarn', '-jvm-target', '17',
                    *map(str, sorted(work.glob('*.kt'))), '-include-runtime', '-d', str(jar)],
                   check=True, timeout=90, stdin=subprocess.DEVNULL)
    # Inspect the production class and all its generated nested classfiles, not the fixture.
    import zipfile
    with zipfile.ZipFile(jar) as archive:
        names = [name[:-6].replace('/', '.') for name in archive.namelist()
                 if name.startswith(PREFIX) and name.endswith('.class')]
    if PREFIX.replace('/', '.') not in names:
        raise RuntimeError('Missing compiled production bubble class')
    bytecode = subprocess.run(['javap', '-classpath', str(jar), '-c', '-p', *names],
                              check=True, capture_output=True, text=True, timeout=45,
                              stdin=subprocess.DEVNULL).stdout
    bad = len(re.findall(r'java/lang/reflect/(?:Method|Executable)\.getParameterCount:', bytecode))
    good = len(re.findall(r'java/lang/reflect/(?:Method|Executable)\.getParameterTypes:', bytecode))
    result = subprocess.run(['java', '-cp', str(jar), 'fixture.DriverKt'],
                            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    checks = re.findall(r'^BUBBLE_BEHAVIOR_PASS checks=(\d+)$', result.stdout, re.M)
    failure = re.search(r'BUBBLE_ASSERT\|([a-z_]+)', result.stderr)
    return {'behavior_exit': result.returncode, 'checks': int(checks[0]) if len(checks) == 1 else 0,
            'failed_assertion': failure.group(1) if failure else None,
            'production_classfiles': len(names), 'getParameterCount': bad,
            'getParameterTypes': good}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, default=ROOT)
    p.add_argument('--mutations', action='store_true')
    args = p.parse_args()
    source = args.source_root / SOURCE
    raw = source.read_bytes()
    with tempfile.TemporaryDirectory(prefix='waex-bubble-reflection-') as folder:
        out = Path(folder)
        result = run_case(raw, out / 'candidate')
        accepted = (result['behavior_exit'] == 0 and result['checks'] == EXPECTED_CHECKS
                    and result['getParameterCount'] == 0 and result['getParameterTypes'] > 0)
        print(json.dumps({'candidate': result, 'accepted': accepted}), flush=True)
        if not accepted:
            return 1
        if args.mutations:
            variants = [
                ('api26_member', '.parameterTypes.size', '.parameterCount', 3, None),
                ('wrong_border_direction', 'if (method.parameterTypes.size == 3) 1 else 0',
                 'if (method.parameterTypes.size == 3) 0 else 0', 1, 'border_uses_second_outgoing'),
                ('missing_wrapper', 'it.parameterTypes.size in 1..2',
                 'it.parameterTypes.size == 0', 1, 'three_factories'),
                ('overwrite_native_color', 'if (color == NO_COLOR) return',
                 '/* deliberate fixture defect */', 1, 'zero_color_preserves_drawable'),
            ]
            text = raw.decode('utf-8')
            for name, old, new, count, failure in variants:
                if text.count(old) != count:
                    raise RuntimeError('Unexpected mutation anchor: ' + name)
                mutant = run_case(text.replace(old, new).encode('utf-8'), out / name)
                rejected = (mutant['behavior_exit'] != 0 and mutant['failed_assertion'] == failure
                            if failure else mutant['behavior_exit'] == 0 and
                            mutant['checks'] == EXPECTED_CHECKS and mutant['getParameterCount'] == 3)
                print(json.dumps({'mutation': name, **mutant, 'rejected': rejected}), flush=True)
                if not rejected:
                    return 1
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(raw).digest():
        raise RuntimeError('Production source changed during test')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
