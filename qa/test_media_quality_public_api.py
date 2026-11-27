#!/usr/bin/env python3
"""Type-check the real quality sources against the pinned public DexKit API.

Only compile: no host APK, native search, actual hooking or output claim.
The Android/Xposed/base-feature boundaries remain explicit compile fixtures.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path("app/src/main/java/com/waenhancer/xposed")
SOURCES = [PREFIX / p for p in (
    "features/media/MediaQualityBypassHook.java",
    "features/media/MediaHostFingerprint.java",
    "features/media/MediaQualitySelectorContract.java",
    "features/media/ProcessImageQualityContract.java",
    "core/devkit/HookReturnTypeGuard.java",
)]

def sha(p):
    return hashlib.file_digest(p.open("rb"), "sha256").hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dexkit-jar", required=True, type=Path)
    parser.add_argument("--kotlin-stdlib", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    dex, stdlib = a.dexkit_jar.resolve(strict=True), a.kotlin_stdlib.resolve(strict=True)
    if sha(dex) != "195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1":
        raise RuntimeError("Wrong public DexKit API bytes")
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    stage, classes = out / "sources", out / "classes"; classes.mkdir()
    fixture = ROOT / "qa/test_media_quality_contract.py"
    module = ast.parse(fixture.read_text(encoding="utf-8"))
    stubs = next(ast.literal_eval(x.value) for x in module.body if isinstance(x, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "STUBS" for t in x.targets))
    sources = []
    for rel, body in stubs.items():
        if rel.startswith("org/luckypray/") or rel.endswith("/MediaHostFingerprint.java"):
            continue
        if rel == "android/content/Context.java":
            body = ("package android.content; public class Context {public String getPackageName(){return \"fixture\";} "
                    "public android.content.pm.ApplicationInfo getApplicationInfo(){throw new AssertionError(\"No real host in API compile\");}}")
        p = stage / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8"); sources.append(p)
    p = stage / "android/content/pm/ApplicationInfo.java"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("package android.content.pm; public class ApplicationInfo {public String sourceDir;}", encoding="utf-8")
    sources.append(p)
    production = [ROOT / p for p in SOURCES]
    log = out / "javac.log"
    with log.open("xb") as f:
        result = subprocess.run(["javac", "--release", "17", "-encoding", "UTF-8", "-cp",
                                 os.pathsep.join(map(str, [dex, stdlib])), "-d", str(classes),
                                 *map(str, sources), *map(str, production)], stdout=f, stderr=subprocess.STDOUT, timeout=120)
    receipt = dict(accepted=result.returncode == 0, returncode=result.returncode, scope=__doc__,
                   dexkit_types_stubbed=False, api_sha256={str(dex):sha(dex), str(stdlib):sha(stdlib)},
                   compiled_sources={str(p.relative_to(ROOT)):sha(p) for p in production},
                   fixture_sha256=sha(fixture), log_sha256=sha(log))
    (out / "RESULT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt), flush=True)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace"))
        raise SystemExit(result.returncode)

if __name__ == "__main__":
    main()
