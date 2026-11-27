#!/usr/bin/env python3
"""Compile and behaviorally reject call-selector regressions; never place a call."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from android_call_type_test import EXPECTED

ROOT = Path(__file__).resolve().parents[1]
HOOK = Path("app/src/main/java/com/waenhancer/xposed/features/privacy/CallTypeControllerHook.java")
MUTATIONS = (
    ("automatic_call", "new Intent(Intent.ACTION_DIAL,", "new Intent(Intent.ACTION_CALL,",
     "phoneChoiceOnlyOpensAConfirmingDialer"),
    ("stale_peer", " && now.peer.equals(request.peer)", "",
     "changedPeerInvalidatesBothChoices"),
    ("rearmed_failed_install", "            ready.set(false);\n            for (int index = installed.size()",
     "            ready.set(true);\n            for (int index = installed.size()",
     "failedInstallationRollsBackAndCannotReactivateRetainedCallbacks"),
    ("disposed_callbacks_active", "        ready.set(false);\n        installationAttempted = true;",
     "        ready.set(true);\n        installationAttempted = true;",
     "screenDisposalInvalidatesVisibleChoiceAndRetainedCallbacks"),
    ("cancel_starts_whatsapp", "dialog.setOnCancelListener(d -> finish(request));",
     "dialog.setOnCancelListener(d -> continueWhatsApp(request));",
     "cancelAndDismissNeverCallEitherDestination"),
    ("argument_alias", "new Request(site, owner, snapshot, arguments.clone())",
     "new Request(site, owner, snapshot, arguments)",
     "fourArgumentRequestClonesArgumentsAndOnlyPhoneChoiceDials"),
)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="Passing same-source all-suite result.json")
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--sdk-jars", type=Path, required=True)
    parser.add_argument("--dexkit", type=Path, required=True)
    args = parser.parse_args()
    expected_tests = EXPECTED["all"]
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_dependencies = json.loads(args.baseline.with_name("dependency-sha256.json").read_text(encoding="utf-8"))
    if not (baseline.get("accepted") is True and baseline.get("suite") == "all"
            and baseline.get("tests") == baseline.get("expected_tests") == expected_tests
            and baseline.get("junit_exit_code") == baseline.get("failures") == baseline.get("errors") == baseline.get("skipped") == 0):
        raise RuntimeError(f"A complete passing {expected_tests}-case baseline is required")
    for relative, expected in baseline["source_sha256"].items():
        if relative.startswith("generated/"):
            continue
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Baseline source identity changed: " + relative)
    args.out.mkdir(parents=True, exist_ok=False)
    original = (ROOT / HOOK).read_text(encoding="utf-8")
    rows = []
    for name, before, after, expected_method in MUTATIONS:
        if original.count(before) != 1:
            raise RuntimeError("Mutation anchor changed: " + name)
        work = args.out / name
        source = work / "source"
        source.mkdir(parents=True)
        shutil.copytree(ROOT / "app/src", source / "app/src")
        shutil.copyfile(ROOT / "app/build.gradle.kts", source / "app/build.gradle.kts")
        shutil.copyfile(ROOT / "gradle.properties", source / "gradle.properties")
        (source / "qa").mkdir()
        shutil.copytree(ROOT / "qa/fixtures/call_type", source / "qa/fixtures/call_type")
        for relative in ("qa/android_call_type_test.py", "qa/localization_support.py"):
            shutil.copyfile(ROOT / relative, source / relative)
        (source / HOOK).write_text(original.replace(before, after), encoding="utf-8", newline="\n")
        command = [sys.executable, str(ROOT / "qa/android_call_type_test.py"),
            "--source-root", str(source), "--out", str(work / "run"), "--suite", "all",
            "--deps", str(args.deps.resolve()), "--sdk-jars", str(args.sdk_jars.resolve()),
            "--dexkit", str(args.dexkit.resolve()), "--allow-test-failure"]
        with (work / "driver.log").open("w", encoding="utf-8") as output:
            executed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=300)
        receipt = work / "run/result.json"
        if executed.returncode != 0 or not receipt.is_file():
            raise RuntimeError("Mutation did not reach compiled JUnit execution: " + name)
        result = json.loads(receipt.read_text(encoding="utf-8"))
        # Robolectric 4.17 prints the default API 34 case without a suffix.
        expected_names = {expected_method, expected_method + "[24]", expected_method + "[28]"}
        observed = [n for n in result["failed_tests"] if n in expected_names]
        observed_dependencies = json.loads(receipt.with_name("dependency-sha256.json").read_text(encoding="utf-8"))
        if observed_dependencies != baseline_dependencies:
            raise RuntimeError("Mutation dependency identities differ from baseline: " + name)
        accepted = (result["accepted"] is False and result["junit_exit_code"] == 1
            and result["tests"] == result["expected_tests"] == expected_tests
            and result["errors"] == result["skipped"] == 0
            and result["failures"] == result["assertion_failures"]
            and len(observed) == len(expected_names) and set(observed) == expected_names)
        row = dict(name=name, behavioral_rejection=accepted, expected_method=expected_method,
            tests=result["tests"], assertion_failures=result["assertion_failures"],
            errors=result["errors"], skipped=result["skipped"], failed_tests=result["failed_tests"],
            modified_source_sha256=digest(source / HOOK), receipt_sha256=digest(receipt),
            dependency_receipt_sha256=digest(receipt.with_name("dependency-sha256.json")))
        rows.append(row)
        (args.out / "result.json").write_text(json.dumps(dict(complete=False, rows=rows), indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if not accepted:
            raise RuntimeError("Expected causal assertion did not reject: " + name)
    (args.out / "result.json").write_text(json.dumps(dict(complete=True, baseline_sha256=digest(args.baseline),
        count=len(rows), expected_tests=expected_tests,
        baseline_dependency_sha256=digest(args.baseline.with_name("dependency-sha256.json")),
        rows=rows, scope="Offline public compiled fixtures; no real calls or device execution"), indent=2) + "\n")

if __name__ == "__main__":
    main()
