#!/usr/bin/env python3
"""Require the duplicate-registration oracle to reject a shared callback snapshot key.

Runs the same complete-source Robolectric suite against a mechanically mutated,
isolated copy of public production sources. It never modifies the input checkout.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOOK = Path("app/src/main/java/com/waenhancer/xposed/features/conversation/PreserveDeleteForMeHook.kt")
NEEDLE = 'private val previousScopeKey = "$TAG.previousScope.${nextScopeCallbackId.incrementAndGet()}"'
MUTANT = 'private val previousScopeKey = "$TAG.previousScope"'
FAILURE = "The last after callback must restore the original unscoped state"
TEST = "duplicateRegistrationsRetainIndependentInvocationScopeSnapshots"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--sdk-jars", type=Path)
    parser.add_argument("--dexkit", type=Path)
    parser.add_argument("--maven")
    parser.add_argument("--maven-repo", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "mutant-source"
    shutil.copytree(root / "app/src/main/java", source / "app/src/main/java")
    hook = source / HOOK
    original = hook.read_text(encoding="utf-8")
    if original.count(NEEDLE) != 1:
        raise RuntimeError("Candidate scope-key declaration changed; review the negative control")
    hook.write_text(original.replace(NEEDLE, MUTANT), encoding="utf-8")
    command = [sys.executable, str(root / "qa/android_preserved_dispatch_test.py"),
               "--source-root", str(source), "--out", str(out / "run"),
               "--expect-assertion-failures", "3"]
    for option in ("deps", "sdk_jars", "dexkit", "maven", "maven_repo"):
        value = getattr(args, option)
        if value is not None:
            if isinstance(value, Path):
                value = value.resolve()
            command.extend(["--" + option.replace("_", "-"), str(value)])
    result = subprocess.run(command, timeout=1200)
    if result.returncode != 0:
        raise RuntimeError("Shared-key negative control did not complete at the expected assertions")
    report = json.loads((out / "run/result.json").read_text(encoding="utf-8"))
    log = (out / "run/junit.log").read_text(encoding="utf-8")
    if (report["tests"] != 117 or report["failures"] != 3
            or report["assertion_failures"] != 3 or not report["accepted_result"]
            or log.count("java.lang.AssertionError: " + FAILURE) != 3
            or log.count(") " + TEST) != 3):
        raise RuntimeError("Negative control failed for a different reason or did not run every API")
    receipt = {
        "control": "shared-scope-snapshot-key",
        "status": "PASS",
        "interpretation": "Mutant compiled and the duplicate-registration assertion failed on all three APIs.",
        "tests": 117,
        "expected_assertion_failures": 3,
        "original_hook_sha256": hashlib.sha256((root / HOOK).read_bytes()).hexdigest(),
        "mutant_hook_sha256": hashlib.sha256(hook.read_bytes()).hexdigest(),
        "command": command,
        "limits": "A passing negative control validates its behavioral oracle, not the mutated production code.",
    }
    (out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("PASS: shared-key mutant compiled and failed only the three expected scope assertions")


if __name__ == "__main__":
    main()
