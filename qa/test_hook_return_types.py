#!/usr/bin/env python3
"""Run production Java return-type guards against method stubs (no Android SDK)."""
import pathlib
import re
import subprocess
import tempfile
root = pathlib.Path(__file__).resolve().parent.parent
parallel_hook = (root / 'app/src/main/java/com/waenhancer/xposed/features/media/ParallelDownloadingHook.java').read_text()
assert re.search(
    r'if\s*\(HookReturnTypeGuard\.canSetObjectResult\(downloadMethod,\s*proxy\)\)\s*\{\s*param\.setResult\(proxy\);',
    parallel_hook,
), 'Parallel download must not publish a proxy without checking the intercepted method return type'
with tempfile.TemporaryDirectory() as d:
    subprocess.run(["javac", "-d", d,
                    str(root / "app/src/main/java/com/waenhancer/xposed/core/devkit/HookReturnTypeGuard.java"),
                    str(root / "qa/TestHookReturnTypeGuard.java")], check=True)
    subprocess.run(["java", "-cp", d, "TestHookReturnTypeGuard"], check=True)
