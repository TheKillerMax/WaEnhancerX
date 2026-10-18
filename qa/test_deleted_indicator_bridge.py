#!/usr/bin/env python3
"""Run actual AntiRevoke preference-reader methods against the real bridge.

Getter bodies are copied verbatim into a JVM harness; Android IO/color types are
explicit doubles. Also exercises strict SharedPreferences type-mismatch behavior.
"""
from pathlib import Path
import argparse
import ast
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "app/src/main/java/com/waenhancer"
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=src / "xposed/features/privacy/AntiRevokeHook.java")
parser.add_argument("--scenario", choices=["all", "color", "type"], default="all")
args = parser.parse_args()
source = args.source.read_text()


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
import java.util.*;
import java.lang.reflect.Proxy;
public final class IndicatorBridgeChecks {
    private final SharedPreferences prefs;
    private IndicatorBridgeChecks(SharedPreferences prefs) { this.prefs = prefs; }
    COLOR_METHOD
    TYPE_METHOD
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
                    if (name.equals("getString") || name.equals("getInt")) throw new ClassCastException();
                    throw new AssertionError("unexpected getter " + name);
                });
    }
    static IndicatorBridgeChecks reader(boolean bridge, String key, Object value) {
        Map<String, Object> values = new HashMap<>();
        if (value != null) values.put(key, value);
        return new IndicatorBridgeChecks(bridge
                ? new PreferenceBridgeClient(new Ctx(values), null)
                : strict(values));
    }
    public static void main(String[] args) {
        String scenario = args.length == 0 ? "all" : args[0];
        for (boolean bridge : new boolean[]{true, false}) {
            if (!scenario.equals("type")) {
                Object[] raw = {0xff11aa44, "#112233", "#80112233", Integer.toString(0xff11aa44), "bad", false, null};
                int[] expected = {0xff11aa44, 0xff112233, 0x80112233, 0xff11aa44, 0xffef4444, 0xffef4444, 0xffef4444};
                for (int i = 0; i < raw.length; i++)
                    check(reader(bridge, "deleted_message_color", raw[i]).getDeletedMessageColor() == expected[i],
                            "canonical/legacy color " + i + " through " + (bridge ? "real bridge" : "strict preferences"));
            }
            if (!scenario.equals("color")) {
                Object[] raw = {0, 1, 2, "0", "1", "2", "bad", false, null};
                int[] expected = {0, 1, 2, 0, 1, 2, 2, 2, 2};
                for (int i = 0; i < raw.length; i++)
                    check(reader(bridge, "anti_revoke_indicator", raw[i]).getIndicatorType() == expected[i],
                            "canonical/legacy indicator " + i + " through " + (bridge ? "real bridge" : "strict preferences"));
            }
        }
        System.out.println("PASS: " + checks + " verbatim AntiRevoke readers / real bridge / strict preference checks");
    }
}
'''.replace("COLOR_METHOD", method("private int getDeletedMessageColor()")).replace(
    "TYPE_METHOD", method("private int getIndicatorType()"))

with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    paths = []
    for name, text in stubs.items():
        path = temp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths.append(str(path))
    subprocess.run(["javac", "--release", "17", "-d", folder, *paths,
                    str(src / "xposed/bridge/client/PreferenceBridgeClient.java")], check=True)
    subprocess.run(["java", "-cp", folder, "test.IndicatorBridgeChecks", args.scenario], check=True)
