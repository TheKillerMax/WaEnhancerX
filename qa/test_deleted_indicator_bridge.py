#!/usr/bin/env python3
"""Run actual AntiRevoke preference-reader methods against the real bridge.

Getter bodies are copied verbatim into a JVM harness; Android IO/color types are
explicit doubles. Also exercises strict SharedPreferences type-mismatch behavior.
"""
from pathlib import Path
import argparse
import ast
import os
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "app/src/main/java/com/waenhancer"
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=src / "xposed/features/privacy/AntiRevokeHook.java")
parser.add_argument("--registry-source", type=Path, default=src / "xposed/core/FeatureRegistry.java")
parser.add_argument("--scenario", choices=["all", "color", "type", "status", "registry"], default="all")
args = parser.parse_args()
source = args.source.read_text()


def method(signature, source=source):
    assert source.count(signature) == 1, signature
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("Unterminated production reader")


base = (src / "xposed/core/BaseFeature.kt").read_text()
scoped_method = method("private fun scopedKey(key: String): String?", base)
enabled_method = method("protected fun isEnabled(key: String, def: Boolean = false): Boolean", base)
registry = args.registry_source.read_text()
registration = registry.split('registerFeature(AntiRevokeHook.class, "Privacy",', 1)[1].split(
    '() -> new AntiRevokeHook(context, classLoader, prefs)', 1)[0].strip()
assert registration.endswith(",")
enabled_lambda = registration[:-1].rstrip()
assert enabled_lambda.startswith("() -> ")
registry_method = method("private static boolean isEntryEnabled(FeatureEntry entry)", registry)
install_method = method("private void installLocked(FeatureEntry entry)", registry)
disabled_guard = re.search(r'if \(entry\.factory == null \|\| !isEntryEnabled\(entry\)\) \{(.*?)\n        \}', install_method, re.S)
assert disabled_guard and "markDisabled(entry);" in disabled_guard.group(1)
assert "return;" in disabled_guard.group(1)
assert install_method.index(disabled_guard.group()) < install_method.index("entry.factory.create()")
shared_signature = "public static boolean isAntiRevokeStatusEnabled(Context context, SharedPreferences prefs)"
shared_method = method(shared_signature) if shared_signature in source else ""
base_fixture = """package test
import android.content.Context
import android.content.SharedPreferences
import java.util.concurrent.ConcurrentHashMap
open class StatusReaderBase(
    @JvmField protected val context: Context,
    @JvmField protected val prefs: SharedPreferences
) {
    companion object { private val scopedKeys = ConcurrentHashMap<String, String>() }
""" + scoped_method + "\n" + enabled_method + "\n}\n"

# Reuse only literal platform doubles; importing the suite would execute tests.
tree = ast.parse((root / "qa/test_bridge_contract.py").read_text())
stubs = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "STUBS"
                                           for target in node.targets):
        stubs = ast.literal_eval(node.value)
assert stubs is not None
stubs = {name: text for name, text in stubs.items() if not name.startswith("test/")}
stubs["android/graphics/Color.java"] = r'''package android.graphics;
public final class Color {
    public static int parseColor(String value) {
        if (value == null || !(value.length() == 7 || value.length() == 9) || value.charAt(0) != '#')
            throw new IllegalArgumentException("unsupported fixture color");
        long color = Long.parseLong(value.substring(1), 16);
        return (int)(value.length() == 7 ? color | 0xff000000L : color);
    }
}
'''
stubs["test/AntiRevokeHook.java"] = r'''package test;
import android.content.*;
import android.database.ContentObserver;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
import com.waenhancer.xposed.utils.HookErrors;
import java.util.*;
import java.lang.reflect.Proxy;
public final class AntiRevokeHook extends StatusReaderBase {
    private AntiRevokeHook(Context context, SharedPreferences prefs) { super(context, prefs); }
    COLOR_METHOD
    TYPE_METHOD
    STATUS_METHOD
    SHARED_STATUS_METHOD
    @FunctionalInterface interface FeatureEnabled { boolean isEnabled(); }
    static class FeatureEntry {
        final FeatureEnabled enabled; String error;
        FeatureEntry(FeatureEnabled enabled) { this.enabled = enabled; }
    }
    REGISTRY_METHOD
    private boolean registryEnabled() { return isEntryEnabled(new FeatureEntry(REGISTRY_LAMBDA)); }
    static int checks;
    static void check(boolean value, String message) { checks++; if (!value) throw new AssertionError(message); }
    static class Resolver extends ContentResolver {
        final Map<String, Object> values;
        Resolver(Map<String, Object> values) { this.values = values; }
        public void registerContentObserver(Uri uri, boolean descendants, ContentObserver observer) {}
        public Bundle call(Uri uri, String method, String arg, Bundle extras) {
            if (!"get_all_preferences".equals(method)) throw new AssertionError(method);
            Bundle result = new Bundle(), data = new Bundle();
            for (Map.Entry<String, Object> e : values.entrySet()) {
                if (e.getValue() instanceof String) data.putString(e.getKey(), (String)e.getValue());
                else if (e.getValue() instanceof Integer) data.putInt(e.getKey(), (Integer)e.getValue());
                else if (e.getValue() instanceof Boolean) data.putBoolean(e.getKey(), (Boolean)e.getValue());
                else if (e.getValue() instanceof Long) data.putLong(e.getKey(), (Long)e.getValue());
                else if (e.getValue() instanceof Float) data.putFloat(e.getKey(), (Float)e.getValue());
                else throw new AssertionError("unsupported fixture value");
            }
            result.putBundle("values", data);
            return result;
        }
    }
    static class Ctx extends Context {
        final Resolver resolver; final String packageName;
        Ctx(Map<String, Object> values) { this(values, "com.whatsapp"); }
        Ctx(Map<String, Object> values, String packageName) { resolver = new Resolver(values); this.packageName = packageName; }
        public ContentResolver getContentResolver() { return resolver; }
        public String getPackageName() { return packageName; }
    }
    static SharedPreferences strict(Map<String, Object> values) {
        return (SharedPreferences)Proxy.newProxyInstance(AntiRevokeHook.class.getClassLoader(),
                new Class<?>[]{SharedPreferences.class}, (proxy, method, args) -> {
                    String name = method.getName();
                    if (name.equals("getAll")) return new HashMap<>(values);
                    String key = (String)args[0];
                    if (name.equals("contains")) return values.containsKey(key);
                    Object value = values.get(key);
                    if (value == null) return args[1];
                    if (name.equals("getString") && value instanceof String) return value;
                    if (name.equals("getInt") && value instanceof Integer) return value;
                    if (name.equals("getBoolean") && value instanceof Boolean) return value;
                    if (name.equals("getString") || name.equals("getInt") || name.equals("getBoolean")) throw new ClassCastException();
                    throw new AssertionError("unexpected getter " + name);
                });
    }
    static AntiRevokeHook reader(boolean bridge, String key, Object value) {
        Map<String, Object> values = new HashMap<>();
        if (value != null) values.put(key, value);
        return reader(bridge, values, "com.whatsapp");
    }
    static AntiRevokeHook reader(boolean bridge, Map<String, Object> values, String packageName) {
        Ctx context = new Ctx(values, packageName);
        return new AntiRevokeHook(context, bridge
                ? new PreferenceBridgeClient(context, null) : strict(values));
    }
    public static void main(String[] args) {
        String scenario = args.length == 0 ? "all" : args[0];
        for (boolean bridge : new boolean[]{true, false}) {
            if (scenario.equals("all") || scenario.equals("color")) {
                Object[] raw = {0xff11aa44, "#112233", "#80112233", Integer.toString(0xff11aa44), "bad", false, null};
                int[] expected = {0xff11aa44, 0xff112233, 0x80112233, 0xff11aa44, 0xffef4444, 0xffef4444, 0xffef4444};
                for (int i = 0; i < raw.length; i++)
                    check(reader(bridge, "deleted_message_color", raw[i]).getDeletedMessageColor() == expected[i],
                            "canonical/legacy color " + i + " through " + (bridge ? "real bridge" : "strict preferences"));
            }
            if (scenario.equals("all") || scenario.equals("type")) {
                Object[] raw = {0, 1, 2, "0", "1", "2", "bad", false, null};
                int[] expected = {0, 1, 2, 0, 1, 2, 2, 2, 2};
                for (int i = 0; i < raw.length; i++)
                    check(reader(bridge, "anti_revoke_indicator", raw[i]).getIndicatorType() == expected[i],
                            "canonical/legacy indicator " + i + " through " + (bridge ? "real bridge" : "strict preferences"));
            }
        }
        if (scenario.equals("all") || scenario.equals("status") || scenario.equals("registry")) {
            Object[] values = {"1", "0", "true", "TrUe", "false", "FALSE", "", "invalid", "2", " 1 ",
                    true, false, 1, 0, 2, -1, 1L, 0L, 4294967297L, 1.0f, null};
            boolean[] expected = {true, false, true, true, false, false, false, false, false, false,
                    true, false, true, false, false, false, true, false, false, false, false};
            for (boolean bridge : new boolean[]{true, false}) {
                for (int i = 0; i < values.length; i++) {
                    AntiRevokeHook current = reader(bridge, "antirevokestatus", values[i]);
                    if (!scenario.equals("registry"))
                        check(current.isAntiRevokeStatusEnabled() == expected[i],
                                "status reader case " + i + " bridge=" + bridge);
                    if (!scenario.equals("status"))
                        check(current.registryEnabled() == expected[i],
                                "status-only registry case " + i + " bridge=" + bridge);
                }
                String key = "antirevokestatus";
                Map<String, Object> scoped = new HashMap<>();
                scoped.put("com.whatsapp:" + key, "1");
                scoped.put("com.whatsapp.w4b:" + key, "0");
                AntiRevokeHook own = reader(bridge, scoped, "com.whatsapp");
                AntiRevokeHook other = reader(bridge, scoped, "com.whatsapp.w4b");
                check(own.isAntiRevokeStatusEnabled(), "own scoped status must enable");
                check(!other.isAntiRevokeStatusEnabled(), "other package status must not leak");
                check(own.registryEnabled(), "status-only scoped registry must install");
                check(!other.registryEnabled(), "other package registry must stay disabled");
                scoped.put(key, "0");
                own = reader(bridge, scoped, "com.whatsapp");
                check(!own.isAntiRevokeStatusEnabled() && !own.registryEnabled(),
                        "explicit root false must override scoped true");
                scoped.put(key, "invalid");
                own = reader(bridge, scoped, "com.whatsapp");
                check(!own.isAntiRevokeStatusEnabled() && !own.registryEnabled(),
                        "invalid root must not fall through to scoped true");
                scoped.remove(key);
                scoped.remove("com.whatsapp:" + key);
                own = reader(bridge, scoped, "com.whatsapp");
                check(!own.isAntiRevokeStatusEnabled() && !own.registryEnabled(),
                        "foreign-only scope cannot enable current package");
                check(!reader(bridge, scoped, null).isAntiRevokeStatusEnabled(),
                        "missing package without root key stays disabled");
                check(!reader(bridge, scoped, "").isAntiRevokeStatusEnabled(),
                        "empty package without root key stays disabled");
                for (String messageKey : new String[]{"anti_revoke", "preserve_own_revoke"}) {
                    Map<String, Object> message = new HashMap<>();
                    message.put(messageKey, true);
                    message.put(key, "invalid");
                    check(reader(bridge, message, "com.whatsapp").registryEnabled(),
                            "existing message activation gate retained: " + messageKey);
                }
            }
            SharedPreferences unreadable = (SharedPreferences)Proxy.newProxyInstance(
                    AntiRevokeHook.class.getClassLoader(), new Class<?>[]{SharedPreferences.class},
                    (proxy, method, arguments) -> { throw new IllegalStateException("read unavailable"); });
            check(!new AntiRevokeHook(new Ctx(new HashMap<>()), unreadable).isAntiRevokeStatusEnabled(),
                    "unreadable preferences must fail closed");
            AssertionError fatal = new AssertionError("fixture assertion must propagate");
            SharedPreferences broken = (SharedPreferences)Proxy.newProxyInstance(
                    AntiRevokeHook.class.getClassLoader(), new Class<?>[]{SharedPreferences.class},
                    (proxy, method, arguments) -> { throw fatal; });
            Throwable escaped = null;
            try { new AntiRevokeHook(new Ctx(new HashMap<>()), broken).isAntiRevokeStatusEnabled(); }
            catch (Throwable error) { escaped = error; }
            check(escaped == fatal, "unexpected preference assertion must propagate");
        }
        System.out.println("PASS: " + checks + " verbatim AntiRevoke readers / real bridge / strict preference checks");
    }
}
'''.replace("COLOR_METHOD", method("private int getDeletedMessageColor()")).replace(
    "TYPE_METHOD", method("private int getIndicatorType()")).replace(
    "SHARED_STATUS_METHOD", shared_method).replace(
    "STATUS_METHOD", method("private boolean isAntiRevokeStatusEnabled()")).replace(
    "REGISTRY_METHOD", registry_method).replace("REGISTRY_LAMBDA", enabled_lambda)

with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    paths = []
    for name, text in stubs.items():
        path = temp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if name != "test/AntiRevokeHook.java":
            paths.append(str(path))
    subprocess.run(["javac", "--release", "17", "-d", folder, *paths,
                    str(src / "xposed/bridge/client/PreferenceBridgeClient.java"),
                    str(src / "config/PreferenceSchema.java"),
                    str(src / "xposed/utils/HookErrors.java")], check=True)
    base_path = temp / "test/StatusReaderBase.kt"
    base_path.write_text(base_fixture, encoding="utf-8")
    compiler = Path(shutil.which("kotlinc") or "kotlinc").resolve()
    kotlin_home = Path(os.environ.get("KOTLIN_HOME", str(compiler.parent.parent)))
    subprocess.run([str(compiler), str(base_path), "-classpath", folder,
                    "-jvm-target", "17", "-d", folder], check=True)
    classpath = os.pathsep.join([folder, str(kotlin_home / "lib/kotlin-stdlib.jar")])
    subprocess.run(["javac", "--release", "17", "-cp", classpath, "-d", folder,
                    str(temp / "test/AntiRevokeHook.java")], check=True)
    print("COMPILE_OK: actual BaseFeature readers, registry predicate and preference bridge", flush=True)
    subprocess.run(["java", "-cp", classpath, "test.AntiRevokeHook", args.scenario], check=True)
