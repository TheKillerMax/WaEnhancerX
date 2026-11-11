#!/usr/bin/env python3
"""Compile and exercise the actual WAEX message-ID methods against JVM host doubles.

This is a source-fragment contract test, not an Android/WhatsApp runtime test.
"""

from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "app/src/main/java/com/waenhancer/xposed/features/conversation/MessageDeviceSourceHook.java"


def extract_method(source: str, declaration: str) -> str:
    start = source.index(declaration)
    opening = source.index("{", start)
    depth = 0
    for position in range(opening, len(source)):
        character = source[position]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : position + 1]
    raise AssertionError("Unterminated Java method: " + declaration)


HARNESS = r'''
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.regex.Pattern;

public final class MessageIdFallbackHarness {
    /* ACTUAL_WAEX_METHODS */

    private static final class MessageKey {
        private final String A00;
        MessageKey(String id) { A00 = id; }
    }

    private static class BaseMessage {
        private final MessageKey A11 = new MessageKey("INHERITED_123456789");
    }

    private static final class ChildMessage extends BaseMessage { }

    private static final class KeyMessage {
        private final MessageKey A11;
        KeyMessage(String id) { A11 = new MessageKey(id); }
    }

    private static final class StaticKeyMessage {
        private static final MessageKey CONSTANT_KEY = new MessageKey("WRONG_STATIC_123456");
        @Override public String toString() { return "messageId=CORRECT_FALLBACK_123456"; }
    }

    private static final class KeyWithStaticString {
        private static final String CONSTANT = "WRONG_STATIC_654321";
        private final String A00 = "CORRECT_INSTANCE_654321";
    }

    private static final class MessageWithStaticKeyString {
        private final KeyWithStaticString A11 = new KeyWithStaticString();
    }

    private static final class FallbackMessage {
        private final String text;
        FallbackMessage(String text) { this.text = text; }
        @Override public String toString() { return text; }
    }

    private int cases = 0;
    private int passed = 0;

    private void check(String name, Object message, String expected) {
        ++cases;
        String actual = extractMessageId(message);
        if (java.util.Objects.equals(expected, actual)) {
            ++passed;
            System.out.println("PASS " + name);
        } else {
            System.out.println("FAIL " + name + " expected=" + expected + " actual=" + actual);
        }
    }

    public static void main(String[] args) {
        MessageIdFallbackHarness test = new MessageIdFallbackHarness();
        test.check("null", null, null);
        test.check("direct_obfuscated_key", new KeyMessage("KEY_123456789"), "KEY_123456789");
        test.check("inherited_obfuscated_key", new ChildMessage(), "INHERITED_123456789");
        test.check("invalid_short_key", new KeyMessage("short"), null);
        test.check("static_message_key_ignored", new StaticKeyMessage(), "CORRECT_FALLBACK_123456");
        test.check("static_key_payload_ignored", new MessageWithStaticKeyString(), "CORRECT_INSTANCE_654321");
        test.check("fallback_messageId", new FallbackMessage("Message(messageId=ABC_123456789)"), "ABC_123456789");
        test.check("fallback_messageID", new FallbackMessage("Message(messageID=ABC_987654321)"), "ABC_987654321");
        test.check("fallback_keyId", new FallbackMessage("Message(keyId=KEY_987654321, device=2)"), "KEY_987654321");
        test.check("fallback_Key_parenthesized", new FallbackMessage("Message(Key(id)=KEY_123456789)"), "KEY_123456789");
        test.check("unrelated_toString", new FallbackMessage("Message(unrelated=ABC_123456789)"), null);
        test.check("unsupported_delimiter", new FallbackMessage("Message(messageId:ABC_123456789)"), null);
        // Java modules disallow deep reflection into String on modern JVMs.
        test.check("inaccessible_reflection_does_not_abort_fallback", "messageId=STRING_123456789", "STRING_123456789");
        System.out.println("TOTAL " + test.passed + "/" + test.cases);
        if (test.passed != test.cases) System.exit(1);
    }
}
'''


def run_methods(methods: str) -> tuple[int, str]:
    harness = HARNESS.replace("/* ACTUAL_WAEX_METHODS */", methods)
    with tempfile.TemporaryDirectory(prefix="waex-message-id-") as tmp:
        java_file = Path(tmp) / "MessageIdFallbackHarness.java"
        java_file.write_text(harness, encoding="utf-8")
        compile_cmd = [
            "java", "-m", "jdk.compiler/com.sun.tools.javac.Main", "-source", "17",
            "-target", "17", "-d", tmp, str(java_file),
        ]
        subprocess.run(compile_cmd, check=True, timeout=30)
        execute_cmd = ["java", "-cp", tmp, "MessageIdFallbackHarness"]
        result = subprocess.run(execute_cmd, check=False, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    methods = "\n".join(
        extract_method(source, declaration)
        for declaration in (
            "private String extractMessageId(Object messageObj)",
            "private String extractIdFromKeyObj(Object keyObj)",
        )
    )
    code, output = run_methods(methods)
    print(output, end="")
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
