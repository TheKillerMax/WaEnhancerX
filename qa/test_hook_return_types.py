#!/usr/bin/env python3
"""Run production Java return-type guards against method stubs (no Android SDK)."""
import pathlib
import subprocess
import tempfile
root = pathlib.Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as d:
    subprocess.run(["javac", "-d", d,
                    str(root / "app/src/main/java/com/waenhancer/xposed/core/devkit/HookReturnTypeGuard.java"),
                    str(root / "qa/TestHookReturnTypeGuard.java")], check=True)
    subprocess.run(["java", "-cp", d, "TestHookReturnTypeGuard"], check=True)
