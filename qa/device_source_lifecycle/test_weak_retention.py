#!/usr/bin/env python3
"""Compile exact production row binding against a weak-key Xposed model."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import test_listener_ownership as common

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1] / common.RELATIVE


def execute(source, output):
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    marker = "    private static final class DeviceSourceRowBinding"
    cls, class_lines = common.extract_block(text, marker)
    match = re.search(r"^    private [^\n]*\btrackDeviceSourceTarget\(", text, re.M)
    method, method_lines = common.extract_block(text, match.group(0))
    generated = (ROOT / "WeakRetentionProbe.java.template").read_text().replace(
        "/* EXACT_ROW_BINDING */", cls + "\n" + method
    )
    output.mkdir(parents=True, exist_ok=True)
    java_file = output / "WeakRetentionProbe.java"
    java_file.write_text(generated)
    java = shutil.which("java")
    compiler = shutil.which("javac")
    has_symbols = (Path(java).resolve().parents[1] / "lib/ct.sym").exists()
    flags = (["--release", "17"] if has_symbols else ["-source", "17", "-target", "17"])
    command = ([compiler] if compiler else [java, "-m", "jdk.compiler/com.sun.tools.javac.Main"]) + flags + [java_file.name]
    built = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=60)
    (output / "compile.log").write_text(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError("Weak retention compile failure is not a negative-control PASS: " + built.stderr)
    observed = subprocess.run([java, "WeakRetentionProbe"], cwd=output, capture_output=True, text=True, timeout=10)
    (output / "run.log").write_text(observed.stdout + observed.stderr)
    cases = [line.split("\t", 1) for line in observed.stdout.splitlines() if "\t" in line]
    result = {
        "schema": "WAEX_WEAK_ROW_BINDING_RETENTION_V1",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "actual_source_intervals": [class_lines, method_lines],
        "fixture_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "compile_command": command,
        "compile_exit_code": built.returncode,
        "run_exit_code": observed.returncode,
        "cases": cases,
        "scope": "JVM weak-key retention simulation of LSPosed additional-instance-field values",
        "limits": "GC behavior depends on the JVM; no Android/ART heap profiling or real LSPosed instance was run",
    }
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2) + "\n")
    if observed.returncode != 0 or len(cases) != 3 or cases[0][1] != "PASS" or cases[1][1] != "PASS":
        raise RuntimeError("Weak-key model gate did not demonstrate collection and negative retention")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = execute(SOURCE, args.out.resolve())
    print("weak key GC control: PASS; entries remaining:", result["cases"][-1][-1])


if __name__ == "__main__":
    main()
