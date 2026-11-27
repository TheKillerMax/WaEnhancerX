#!/usr/bin/env python3
"""Reject compiled media-quality regressions through the unchanged behavior matrix."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HOOK="app/src/main/java/com/waenhancer/xposed/features/media/MediaQualityBypassHook.java"
SOURCES=(HOOK,
    "app/src/main/java/com/waenhancer/xposed/features/media/MediaQualitySelectorContract.java",
    "app/src/main/java/com/waenhancer/xposed/features/media/ProcessImageQualityContract.java",
    "app/src/main/java/com/waenhancer/xposed/features/media/MediaHostFingerprint.java",
    "app/src/main/java/com/waenhancer/xposed/core/devkit/HookReturnTypeGuard.java")
MUTANTS=(
    ("image-quality-ceiling", "if (quality >= 1 && quality <= 100) param.args[0] = 100;",
      "if (quality >= 1 && quality <= 100) param.args[0] = 90;"),
    ("live-gallery-presentation-flag",
      "if (isImageQualityMaxEnabled() || isVideo60FpsEnabled()) param.setResult(true);",
      "param.setResult(true);"),
    ("video-fps-ceiling", "if (original > 0 && original < 60) param.setResult(60);",
      "if (original > 0 && original < 60) param.setResult(50);"),
)
def main():
    original=(ROOT/HOOK).read_text(encoding="utf8")
    for name,before,after in MUTANTS:
        if original.count(before)!=1:raise SystemExit(name+": real source drift")
        with tempfile.TemporaryDirectory(prefix="waex_media_mutant_") as tmp:
            source=Path(tmp)
            for path in SOURCES:
                target=source/path
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/path,target)
            (source/HOOK).write_text(original.replace(before,after),encoding="utf8")
            result=subprocess.run([sys.executable,str(ROOT/"qa/test_media_quality_contract.py"),
                "--source-root",str(source)],capture_output=True,text=True,timeout=100)
            match=re.search(r"RESULT checks=(\d+) failures=(\d+) suite=media",result.stdout)
            if (not match or int(match.group(1))<50 or int(match.group(2))==0
                    or result.returncode==0 or "compilation failed" in result.stdout):
                print(result.stdout[-4000:],result.stderr[-1200:],flush=True)
                raise SystemExit(name+": no compiled behavioral detection")
            print("KILLED "+name+" checks="+match.group(1)+" failures="+match.group(2),flush=True)
    print("PASS three compiled quality-policy negative controls",flush=True)
if __name__=="__main__":main()
