#!/usr/bin/env python3
"""Run actual AntiRevoke preference-reader methods against the real bridge.

Getter bodies are copied verbatim into a JVM harness; Android IO/color types are
explicit doubles. Also exercises strict SharedPreferences type-mismatch behavior.
"""
from pathlib import Path
import argparse
import ast
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "app/src/main/java/com/waenhancer"
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=src / "xposed/features/privacy/AntiRevokeHook.java")
parser.add_argument("--registry", type=Path, default=src / "xposed/core/FeatureRegistry.java")
parser.add_argument("--schema", type=Path, default=src / "config/PreferenceSchema.java")
parser.add_argument("--scenario", choices=["all", "color", "type", "status"], default="all")
args = parser.parse_args()
source = args.source.read_text(encoding="utf-8")
registry = args.registry.read_text(encoding="utf-8")
registry_expressions = re.findall(
    r'registerFeature\(AntiRevokeHook\.class, "Privacy",\s*\(\) -> (.*?)'
    r',\s*\(\) -> new AntiRevokeHook\(', registry, flags=re.DOTALL)
assert len(registry_expressions) == 1, "Expected one AntiRevoke registration predicate"


def method(signature):
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
stubs["test/IndicatorBridgeChecks.java"] = r'''package test;
import android.content.*;
import android.database.ContentObserver;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
import com.waenhancer.xposed.utils.HookErrors;
import com.waenhancer.config.PreferenceSchema;
import java.util.*;
import java.lang.reflect.Proxy;
public final class IndicatorBridgeChecks {
    private final SharedPreferences prefs;
    private IndicatorBridgeChecks(SharedPreferences prefs) { this.prefs = prefs; }
    COLOR_METHOD
    TYPE_METHOD
    STATUS_METHOD
    private boolean registryEnabled() { return REGISTRY_EXPRESSION; }
    static int checks;
    static void check(boolean value, String message) { checks++; if (!value) throw new AssertionError(message); }
    static class Resolver extends ContentResolver {
        final Map<String, Object> values;
        Resolver(Map<String, Object> values) { this.values = values; }
        public void registerContentObserver(Uri uri, boolean descendants, ContentObserver observer) {}
        public Bundle call(Uri uri, String method, String arg, Bundle extras) {
            if (!"get_all_preferences".equals(method)) throw new AssertionError(method);
            if (values == null) return null; // Explicit unavailable IPC for disk fallback.
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
        final Resolver resolver;
        Ctx(Map<String, Object> values) { resolver = new Resolver(values); }
        public ContentResolver getContentResolver() { return resolver; }
        public String getPackageName() { return "example.fixture.indicator"; }
    }
    static SharedPreferences strict(Map<String, Object> values) {
        return (SharedPreferences)Proxy.newProxyInstance(IndicatorBridgeChecks.class.getClassLoader(),
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
                    if (name.equals("getString") || name.equals("getInt") || name.equals("getBoolean"))
                        throw new ClassCastException();
                    throw new AssertionError("unexpected getter " + name);
                });
    }
    static IndicatorBridgeChecks reader(boolean bridge, String key, Object value) {
        Map<String, Object> values = new HashMap<>();
        if (value != null) values.put(key, value);
        return reader(bridge, values);
    }
    static IndicatorBridgeChecks reader(boolean bridge, Map<String, Object> values) {
        return new IndicatorBridgeChecks(bridge
                ? new PreferenceBridgeClient(new Ctx(values), null)
                : strict(values));
    }
    static IndicatorBridgeChecks diskReader(Map<String, Object> raw) {
        PreferenceBridgeClient bridge = new PreferenceBridgeClient(new Ctx(null), strict(raw));
        check("DISK_FALLBACK".equals(bridge.getLastSyncSource()), "must exercise real disk fallback");
        return new IndicatorBridgeChecks(bridge);
    }
    static void status(IndicatorBridgeChecks reader, boolean expected, String label) {
        check(reader.isAntiRevokeStatusEnabled() == expected, "STATUS_CONTRACT event " + label);
        check(reader.registryEnabled() == expected, "STATUS_CONTRACT registration " + label);
    }
    static void statusTests() {
        Object[] on = {"1", "true", "TRUE", true, 1, 1L, 1.0f};
        Object[] off = {"0", "false", "FALSE", false, 0, 0L, 0.0f, null,
                "", "2", " 1", "junk", 2, -1, 1.5f, Float.NaN, Float.POSITIVE_INFINITY};
        for (boolean bridge : new boolean[]{true, false}) {
            for (int i = 0; i < on.length; i++)
                status(reader(bridge, "antirevokestatus", on[i]), true, "ON " + i + " bridge=" + bridge);
            for (int i = 0; i < off.length; i++)
                status(reader(bridge, "antirevokestatus", off[i]), false, "OFF " + i + " bridge=" + bridge);
            for (String other : List.of("anti_revoke", "preserve_own_revoke")) {
                IndicatorBridgeChecks separate = reader(bridge, Map.of(other, true, "antirevokestatus", "0"));
                check(separate.registryEnabled(), "STATUS_CONTRACT other registration " + other);
                check(!separate.isAntiRevokeStatusEnabled(), "STATUS_CONTRACT independent status " + other);
            }
        }
        String key = "antirevokestatus";
        String own = "example.fixture.indicator:" + key;
        String other = "example.fixture.other:" + key;
        String mode = "module_config_mode";
        status(diskReader(Map.of(mode, "Universal", own, "1")), false, "Universal ignores stale target");
        status(diskReader(Map.of(mode, "Universal", key, "0", own, "1")), false, "Universal explicit OFF");
        status(diskReader(Map.of(mode, "Per Target App", key, "1", own, "0")), false, "target OFF overrides root ON");
        status(diskReader(Map.of(mode, "Per Target App", key, "0", own, "1")), true, "target ON overrides root OFF");
        status(diskReader(Map.of(mode, "Per Target App", other, "1")), false, "other target isolated");
        status(diskReader(Map.of(mode, "Per Target App", key, "1", other, "0")), true, "root fallback");
        status(diskReader(Map.of(mode, "Per Target App", key, "1", own, "broken")), false, "invalid own fails closed");
        status(reader(true, Map.of(mode, "Per Target App", key, "0", own, "1")), false,
                "provider effective OFF is not re-resolved");
        Map<String, Object> live = new HashMap<>();
        live.put(key, "1");
        IndicatorBridgeChecks active = reader(true, live);
        status(active, true, "live initial ON");
        live.put(key, "0");
        ((PreferenceBridgeClient) active.prefs).syncPreferences();
        status(active, false, "live OFF after refresh");
        live.remove(key);
        ((PreferenceBridgeClient) active.prefs).syncPreferences();
        status(active, false, "live missing after refresh");
        check(!PreferenceSchema.isStatusAntiRevokeEnabled(Set.of("1")), "STATUS_CONTRACT reject set");
        check(PreferenceSchema.isStatusAntiRevokeEnabled(1.0d), "STATUS_CONTRACT legacy JSON double ON");
        check(!PreferenceSchema.isStatusAntiRevokeEnabled(0.999d), "STATUS_CONTRACT reject fractional double");
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
        if (scenario.equals("all") || scenario.equals("status")) statusTests();
        System.out.println("PASS: " + checks + " verbatim AntiRevoke readers / real bridge / strict preference checks");
    }
}
'''.replace("COLOR_METHOD", method("private int getDeletedMessageColor()")).replace(
    "TYPE_METHOD", method("private int getIndicatorType()")).replace(
    "STATUS_METHOD", method("private boolean isAntiRevokeStatusEnabled()")).replace(
    "REGISTRY_EXPRESSION", registry_expressions[0])

with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    paths = []
    for name, text in stubs.items():
        path = temp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths.append(str(path))
    subprocess.run(["javac", "--release", "17", "-d", folder, *paths,
                    str(src / "xposed/bridge/client/PreferenceBridgeClient.java"),
                    str(args.schema),
                    str(src / "xposed/utils/HookErrors.java")], check=True)
    subprocess.run(["java", "-cp", folder, "test.IndicatorBridgeChecks", args.scenario], check=True)
