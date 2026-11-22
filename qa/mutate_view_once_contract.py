#!/usr/bin/env python3
"""Confirm the compiled view-once assertions reject two behavioral regressions.

Controls run in disposable source roots, never in the checkout. A compiler failure,
missing fixture, or timeout is not counted as a successful mutation detection.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HOOK = "app/src/main/java/com/waenhancer/xposed/features/privacy/AntiViewOnceHook.java"
CONTRACT = "app/src/main/java/com/waenhancer/xposed/features/privacy/ViewOnceMessageContract.java"
ERRORS = "app/src/main/java/com/waenhancer/xposed/utils/HookErrors.java"
CONTROLS = (
    ("outgoing-identity-must-remain-unchanged",
     "if (messages.isIncoming(param.thisObject)) param.args[0] = 0;",
     "if (true) param.args[0] = 0;"),
    ("live-disabled-setting-must-be-respected",
     'if (!isEnabled("anti_view_once", false) && !isEnabled("viewonce", false)) return;',
     'if (false) return;'),
)

def main():
    original = (ROOT/HOOK).read_text(encoding="utf8")
    for name, before, after in CONTROLS:
        if original.count(before) != 1:
            raise SystemExit(name+": source identity drift, refusing inconclusive mutation")
        with tempfile.TemporaryDirectory(prefix="waex_view_once_mutant_") as tmp:
            root=Path(tmp)
            for relative in (HOOK, CONTRACT, ERRORS):
                out=root/relative
                out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,out)
            (root/HOOK).write_text(original.replace(before,after),encoding="utf8")
            result=subprocess.run([sys.executable,str(ROOT/"qa/test_view_once_contract.py"),
                "--source-root",str(root),"--jid-family","modern"],
                text=True,capture_output=True,timeout=100)
            match=re.search(r"RESULT checks=(\d+) failures=(\d+) suite=viewonce",result.stdout)
            if (not match or int(match.group(1)) < 30 or int(match.group(2)) == 0
                    or result.returncode == 0 or "Real view-once hook/contract compilation failed" in result.stdout):
                print(result.stdout[-4000:],result.stderr[-1200:],flush=True)
                raise SystemExit(name+": NOT rejected by compiled behavior")
            print("KILLED "+name+" checks="+match.group(1)+" behavioral_failures="+match.group(2),flush=True)
    print("PASS both negative controls rejected by real-source behavior",flush=True)

if __name__=="__main__":
    main()
