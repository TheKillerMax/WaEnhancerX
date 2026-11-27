#!/usr/bin/env python3
"""Compile complete view-once hooks and privacy preferences against explicit JVM boundaries.

The fixture exercises reflection, live/scoped preferences and callbacks. Its DexKit
metadata and Xposed registration are doubles, not an Android host acceptance test.
Optional real DexKit/Kotlin jars separately verify the public compilation contract.
No dependency download is attempted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from view_once_boundaries import STUBS

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = (
    "com/waenhancer/xposed/features/privacy/AntiViewOnceHook.java",
    "com/waenhancer/xposed/features/privacy/ViewOnceMessageContract.java",
    "com/waenhancer/xposed/core/privacy/PrivacyPrefs.java",
    "com/waenhancer/xposed/core/privacy/PrivacyToggle.java",
    "com/waenhancer/config/DndPreferencePolicy.java",
)
EXPECTED_CHECKS = 90


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command: list[str], log: Path) -> int:
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=90, check=False)
    return result.returncode


def compile_sources(paths: list[Path], destination: Path, javac: str,
                    classpath: list[Path], log: Path) -> int:
    destination.mkdir()
    args = ["--release", "17", "-encoding", "UTF-8", "-d", str(destination)]
    if classpath:
        args += ["-cp", os.pathsep.join(map(str, classpath))]
    args.extend(map(str, paths))
    # An argument file also keeps long Windows evidence paths out of CreateProcess.
    argfile = log.with_suffix(".args")
    argfile.write_text("\n".join('"' + arg.replace("\\", "/").replace('"', '\\"') + '"'
                                 for arg in args) + "\n", encoding="utf-8")
    return execute([javac, "@" + str(argfile)], log)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jid-family", choices=("modern", "legacy"), default="modern")
    parser.add_argument("--dexkit-jar", type=Path)
    parser.add_argument("--kotlin-stdlib", type=Path)
    args = parser.parse_args()
    if bool(args.dexkit_jar) != bool(args.kotlin_stdlib):
        parser.error("--dexkit-jar and --kotlin-stdlib must be supplied together")
    if args.out.exists():
        parser.error("--out must be a fresh evidence directory")
    args.out.mkdir(parents=True)
    javac, java = shutil.which("javac"), shutil.which("java")
    if not javac or not java:
        raise RuntimeError("Both javac and java are required")
    production = [args.source_root / "app/src/main/java" / name for name in PRODUCTION]
    source_hashes = {name: digest(path) for name, path in zip(PRODUCTION, production)}
    generated = []
    for relative, content in STUBS.items():
        if args.jid_family == "legacy" and relative.startswith("com/whatsapp/infra/core/jid/"):
            relative = relative.replace("com/whatsapp/infra/core/jid/", "com/whatsapp/jid/")
            content = content.replace("com.whatsapp.infra.core.jid", "com.whatsapp.jid")
        path = args.out / "boundaries" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        generated.append(path)
    harness_source = ROOT / "qa/fixtures/view_once/ViewOnceContractTest.java"
    fixture = harness_source.read_text(encoding="utf-8")
    if args.jid_family == "legacy":
        fixture = fixture.replace("com.whatsapp.infra.core.jid", "com.whatsapp.jid")
    harness = args.out / "ViewOnceContractTest.java"
    harness.write_text(fixture, encoding="utf-8")
    compile_code = compile_sources(generated + production + [harness],
                                   args.out / "classes", javac, [], args.out / "compile.log")
    run_code = None
    observed = []
    if compile_code == 0:
        run_code = execute([java, "-cp", str(args.out / "classes"), "ViewOnceContractTest"],
                           args.out / "run.log")
        observed = re.findall(r"^VIEW_ONCE_CHECKS=(\d+) FAILED=(\d+)$",
                              (args.out / "run.log").read_text(encoding="utf-8"), re.M)
    api_code = None
    dependency_hashes = {}
    if args.dexkit_jar:
        dependencies = [args.dexkit_jar, args.kotlin_stdlib]
        dependency_hashes = {str(p): digest(p) for p in dependencies}
        api_boundaries = [p for p in generated if "org/luckypray/" not in p.as_posix()]
        api_code = compile_sources(api_boundaries + production, args.out / "api-classes",
                                   javac, dependencies, args.out / "real-dexkit-api.log")
    unchanged = source_hashes == {name: digest(path) for name, path in zip(PRODUCTION, production)}
    accepted = (compile_code == 0 and run_code == 0
                and observed == [(str(EXPECTED_CHECKS), "0")]
                and unchanged and (api_code is None or api_code == 0))
    result = {
        "accepted": accepted, "jid_family": args.jid_family,
        "compile_exit": compile_code, "run_exit": run_code,
        "expected_checks": EXPECTED_CHECKS, "observed_totals": observed,
        "real_dexkit_compile_exit": api_code,
        "source_root": str(args.source_root.resolve()), "source_sha256": source_hashes,
        "sources_unchanged": unchanged, "dependencies": dependency_hashes,
        "harness_sha256": digest(harness_source),
        "boundaries_sha256": digest(Path(__file__).with_name("view_once_boundaries.py")),
        "limits": "Complete AntiViewOnceHook, ViewOnceMessageContract, PrivacyPrefs, PrivacyToggle "
                  "and DndPreferencePolicy. Reflection and Java execution are real. DexKit queries, "
                  "Android Context/SharedPreferences service boundaries, BaseFeature registration facade "
                  "and Xposed dispatch are explicit doubles. No real DEX query, WhatsApp instance, "
                  "private APK, device modification, message transfer or hosted R13 is established.",
    }
    (args.out / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("accepted", "jid_family", "compile_exit", "run_exit",
                                           "observed_totals", "real_dexkit_compile_exit")}))
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
