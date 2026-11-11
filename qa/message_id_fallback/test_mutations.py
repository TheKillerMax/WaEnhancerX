#!/usr/bin/env python3
"""Negative controls: deliberately break each fix and require the fixture to fail."""

from test_message_id_fallback import SOURCE, extract_method, run_methods


def replace_once(original: str, target: str, replacement: str) -> str:
    if original.count(target) != 1:
        raise RuntimeError(f"Expected exactly one mutation target: {target!r}")
    return original.replace(target, replacement, 1)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    message = extract_method(source, "private String extractMessageId(Object messageObj)")
    key = extract_method(source, "private String extractIdFromKeyObj(Object keyObj)")

    controls = [
        (
            "broken_Key_parenthesized_pattern",
            replace_once(message, r"Key\\(id\\))=", r"Key\\(id)="),
            key,
            "FAIL fallback_Key_parenthesized",
        ),
        (
            "static_message_key_resurrected",
            replace_once(message, "if (Modifier.isStatic(field.getModifiers())) continue;", ""),
            key,
            "FAIL static_message_key_ignored",
        ),
        (
            "static_key_string_resurrected",
            message,
            replace_once(key, "if (Modifier.isStatic(f.getModifiers())) continue;", ""),
            "FAIL static_key_payload_ignored",
        ),
        (
            "inaccessible_field_aborts_fallback",
            replace_once(
                message,
                "// A restricted field must not abort other fields or the text fallback.",
                "return null;",
            ),
            key,
            "FAIL inaccessible_reflection_does_not_abort_fallback",
        ),
    ]

    for label, variant_message, variant_key, expected_failure in controls:
        code, output = run_methods(variant_message + "\n" + variant_key)
        if code != 1 or expected_failure not in output:
            raise RuntimeError(
                f"Negative control {label} not rejected as expected: "
                f"exit={code} expected={expected_failure}\n{output}"
            )
        print(f"PASS negative_control {label} (expected failure observed)")
    print(f"TOTAL NEGATIVE CONTROLS {len(controls)}/{len(controls)}")


if __name__ == "__main__":
    main()
