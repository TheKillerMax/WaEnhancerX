#!/usr/bin/env python3
"""A/B source-fragment regression gate with independently broken variants.

The generated Java compiles exact production method/class bodies against strict
Android/Xposed doubles. This does not build or exercise the WAEX APK.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import test_binding_lifecycle as binding
import test_listener_ownership as ownership
import test_weak_retention as weak_retention

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = ownership.RELATIVE
BASE = "da0ab21533029173b126ce69e2032ee9378e062e"


def mutation(source, old, new):
    occurrences = source.count(old)
    if occurrences != 1:
        raise AssertionError(f"Mutation target occurs {occurrences} times; expected 1: {old[:60]}")
    return source.replace(old, new, 1)


def variants(source):
    yield ("no_returned_row_invalidation", "binding", mutation(
        source, "invalidateDeviceSourceRow((ViewGroup) p.getResult());", "/* mutation: omit returned row cleanup */"))
    convert_cleanup = "invalidateDeviceSourceRow((ViewGroup) p.args[1]);"
    if source.count(convert_cleanup) != 2:
        raise AssertionError("Expected both before and after getView convertView guards")
    yield ("no_prebinding_cleanup", "binding", source.replace(convert_cleanup,
        "/* mutation: omit prebinding cleanup */", 1))
    yield ("no_convert_view_invalidation", "binding", source.replace(convert_cleanup,
        "/* mutation: omit convertView cleanup */"))
    yield ("click_ignores_live_setting", "binding", mutation(
        source, "if (currentDeviceId < 0 || !isEnabled(PREF_KEY, false)", "if (currentDeviceId < 0"))
    yield ("overwrite_foreign_click_action", "ownership", mutation(
        source, "if (current != null && owned == null) return;", "if (false) return;"))
    yield ("accept_detached_async_anchor", "binding", mutation(
        source, "|| findDateTextView(row) != dateTextView) return;", ") return;"))
    yield ("skip_secondary_tracking", "binding", mutation(
        source, "trackDeviceSourceTarget(binding, textView);", "/* mutation: no secondary target tracking */"))
    yield ("forget_rendered_snapshot", "binding", mutation(
        source, "XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_RENDERED_TEXT,\n                    String.valueOf(target.getText()));",
        "/* mutation: forget exact rendered text */"))
    yield ("retain_secondary_on_host_change", "binding", mutation(
        source, "if (!binding.active || binding.anchor == null\n                            || binding.anchor.get() != textView) {",
        "if (false) {"))
    yield ("disable_own_set_text_guard", "binding", mutation(
        source, "String desired = original + suffix;\n        XposedHelpers.setAdditionalInstanceField(target, FIELD_DEVICE_GUARD, true);",
        "String desired = original + suffix;"))
    start = source.index("if (!binding.active || !isEnabled(PREF_KEY, false)")
    end = source.index("return;", start) + len("return;")
    yield ("accept_stale_generation", "binding", source[:start]
           + "if (!isEnabled(PREF_KEY, false)) return;" + source[end:])


def summary(result):
    return {
        "label": result["label"],
        "source_sha256": result["source_sha256"],
        "pass": result["pass_count"],
        "fail": result["fail_count"],
        "failing_cases": [case["name"] for case in result["cases"] if case["status"] == "FAIL"],
        "extracted_intervals": result["extracted_intervals"],
        "compile_command": result["compile_command"],
        "compile_exit_code": result["compile_exit_code"],
        "run_exit_code": result["run_exit_code"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="New or owned evidence directory")
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)

    source_path = ROOT / RELATIVE
    actual = source_path.read_bytes()
    baseline = subprocess.run(
        ["git", "show", f"{BASE}:{RELATIVE.as_posix()}"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    source_text = actual.decode("utf-8")
    results = []
    mutant_results = []
    with tempfile.TemporaryDirectory(prefix="waex-device-source-fixtures-") as temp:
        baseline_file = Path(temp) / "MessageDeviceSourceHook-baseline.java"
        baseline_file.write_bytes(baseline)
        expected = [("baseline", baseline_file), ("candidate", source_path)]
        for label, file in expected:
            a = ownership.execute(label, file, output / "ownership", 17)
            b = binding.execute(label, file, output / "binding", 17)
            results.append({"variant": label, "ownership": summary(a), "binding": summary(b)})
            print(f"{label}: ownership {a['pass_count']}/26; binding {b['pass_count']}/30")

        for label, suite, content in variants(source_text):
            mutant = Path(temp) / f"{label}.java"
            mutant.write_text(content, encoding="utf-8")
            if suite == "ownership":
                tested = ownership.execute(label, mutant, output / "mutants", 17)
            else:
                tested = binding.execute(label, mutant, output / "mutants", 17)
            mutant_results.append({"mutation": label, "suite": suite, **summary(tested)})
            print(f"negative control {label}: {tested['fail_count']} detected failures")

    good = (results[0]["ownership"]["fail"] > 0 and results[0]["binding"]["fail"] > 0
            and results[1]["ownership"]["pass"] == 26 and results[1]["ownership"]["fail"] == 0
            and results[1]["binding"]["pass"] == 30 and results[1]["binding"]["fail"] == 0
            and all(item["fail"] > 0 for item in mutant_results))
    version = subprocess.run(["java", "-version"], capture_output=True, text=True, check=True)
    weak_key = weak_retention.execute(source_path, output / "weak_key_retention")
    # Retention is an acceptance check too, not merely a supplementary receipt.
    good = (good and weak_key["compile_exit_code"] == 0 and weak_key["run_exit_code"] == 0
            and weak_key["cases"][:2] == [["weak_candidate_collected", "PASS"],
                                          ["strong_negative_retained", "PASS"]])
    receipt = {
        "schema": "WAEX_DEVICE_SOURCE_LIFECYCLE_AB_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if good else "FAIL",
        "baseline_git_commit": BASE,
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "candidate_sha256": hashlib.sha256(actual).hexdigest(),
        "java": version.stderr.strip(),
        "source": RELATIVE.as_posix(),
        "cases": {"listener_ownership": 26, "adapter_lifecycle": 30},
        "variants": results,
        "negative_controls": mutant_results,
        "weak_key_retention": weak_key,
        "limitations": [
            "Exact selected source fragments only; not a full app compilation",
            "Android View/Xposed/host adapter/storage/async executor are strict local doubles",
            "No real LSPosed hook injection, WhatsApp UI, user profiles or latency measurements",
            "Reflection of View.mListenerInfo remains Android-version dependent",
        ],
    }
    target = output / "RESULTS.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"gate: {receipt['result']}; receipt: {target}")
    if not good:
        sys.exit(1)


if __name__ == "__main__":
    main()
