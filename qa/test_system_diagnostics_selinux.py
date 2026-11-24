#!/usr/bin/env python3
"""Compile the production SELinux diagnostic with bounded Android/root doubles.

No Android device, su process, SELinux setting or network request is used.
JAVA_HOME and KOTLIN_HOME may select an existing JDK/Kotlin installation.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/com/waenhancer/utils/SystemDiagnostics.kt"
FIXTURES = ROOT / "qa/fixtures"


def resolve_toolchain() -> tuple[Path, Path]:
    suffix = ".exe" if os.name == "nt" else ""
    java_root = os.environ.get("JAVA_HOME")
    java = Path(java_root) / "bin" / ("java" + suffix) if java_root else None
    if java is None or not java.is_file():
        located = shutil.which("java")
        if not located:
            raise RuntimeError("An existing JDK is required; set JAVA_HOME")
        java = Path(located)
    kotlin_root = os.environ.get("KOTLIN_HOME")
    if kotlin_root:
        kotlin = Path(kotlin_root)
    else:
        compiler = shutil.which("kotlinc")
        if not compiler:
            raise RuntimeError("An existing Kotlin compiler is required; set KOTLIN_HOME")
        kotlin = Path(compiler).resolve().parent.parent
    if not (kotlin / "lib" / "kotlin-compiler.jar").is_file():
        raise RuntimeError(f"Kotlin compiler jar not found under {kotlin}")
    return java, kotlin


def execute(args: list[str]) -> dict:
    result = subprocess.run(
        args, capture_output=True, timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.decode("utf-8", "replace"),
        "stderr": result.stderr.decode("utf-8", "replace"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--negative-control", action="store_true",
                        help="Also compile false->Permissive and require behavioral rejection")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    java, kotlin = resolve_toolchain()
    original = SOURCE.read_bytes()
    fixtures = sorted(FIXTURES.glob("selinux_*.kt"))
    if len(fixtures) != 10:
        raise RuntimeError(f"Expected 10 bounded fixtures, found {len(fixtures)}")
    summary = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "production_path": str(SOURCE),
        "production_sha256": hashlib.sha256(original).hexdigest(),
        "java": str(java), "kotlin_home": str(kotlin),
        "fixtures": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in fixtures},
        "cases": {}, "real_android_or_root_execution": False,
    }
    with tempfile.TemporaryDirectory(prefix="waex-selinux-") as directory:
        temporary = Path(directory)

        def run_case(name: str, source: Path) -> dict:
            jar = temporary / (name + ".jar")
            compiled = execute([
                str(java), "-Xmx512m", "-XX:ActiveProcessorCount=2", "-XX:TieredStopAtLevel=1",
                "-cp", str(kotlin / "lib" / "*"), "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                "-kotlin-home", str(kotlin), "-nowarn", str(source),
                *map(str, fixtures), "-include-runtime", "-d", str(jar),
            ])
            if compiled["returncode"] != 0:
                raise RuntimeError(f"{name} compilation failed:\n{compiled['stdout']}{compiled['stderr']}")
            executed = execute([str(java), "-Xmx128m", "-XX:ActiveProcessorCount=2", "-jar", str(jar), "check"])
            return {"compile": compiled, "run": executed}

        normal = run_case("production", SOURCE)
        summary["cases"]["production"] = normal
        output = normal["run"]["stdout"] + normal["run"]["stderr"]
        if normal["run"]["returncode"] != 0 or "PASS SELinux diagnostics JVM checks=" not in output:
            raise RuntimeError(f"Production behavioral checks failed:\n{output}")
        print(output.strip(), flush=True)
        if args.negative_control:
            before = 'if (enforced == true) return "Enforcing"'
            after = 'if (enforced != null) return if (enforced) "Enforcing" else "Permissive"'
            text = original.decode("utf-8")
            if text.count(before) != 1:
                raise RuntimeError("Negative control target must occur exactly once")
            mutant_path = temporary / "SystemDiagnostics.kt"
            mutant_path.write_text(text.replace(before, after), encoding="utf-8")
            mutant = run_case("false-is-permissive", mutant_path)
            summary["cases"]["false-is-permissive"] = mutant
            output = mutant["run"]["stdout"] + mutant["run"]["stderr"]
            if mutant["run"]["returncode"] == 0 or "ambiguous false must not imply permissive" not in output:
                raise RuntimeError(f"Negative control did not fail at the intended behavior:\n{output}")
            print("PASS negative control: compiled false->Permissive rejected by behavioral assertion", flush=True)
    if SOURCE.read_bytes() != original:
        raise RuntimeError("Production source changed during verification")
    summary.update(status="PASS", finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    if args.report_dir:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
