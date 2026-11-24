#!/usr/bin/env python3
"""Reject behavioral mutations of the extracted *production* edit-history callbacks.

Mutation only takes place in a disposable file. Compile failures never count as kills.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"app/src/main/java/com/waenhancer/xposed/features/conversation/AntiEditMessagesHook.kt"
HARNESS=ROOT/"qa/test_edit_history_adapter_binding.py"
MUTATIONS={
    "captured_installer_adapter": (
        "val boundAdapter = p.thisObject as? ListAdapter ?: return",
        "val boundAdapter = adapter"),
    "stale_recycled_label": (
        "invalidateEditLabelBinding(editLabel)",
        "if (false) invalidateEditLabelBinding(editLabel)"),
    "original_key_mapping_omitted": (
        "keyId = editStore.resolveOriginalKey(keyId)",
        "keyId = keyId"),
    "canonical_database_on_scroll": (
        "val rowId = if (keyId.isNullOrEmpty()) extractRowId(item) else 0L",
        "val rowId = resolveCanonicalRowId(extractRowId(item), keyId)"),
}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    original=SOURCE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="waex_edit_binding_mutants_") as temp:
        tmp=Path(temp)
        results=[]
        for name,(anchor,replacement) in MUTATIONS.items():
            n=original.count(anchor)
            if n!=1:
                raise AssertionError(f"Expected one source anchor for {name}, got {n}")
            mutant=tmp/(name+".kt")
            mutant.write_text(original.replace(anchor,replacement,1),encoding="utf-8")
            r=subprocess.run([sys.executable,str(HARNESS),"--source",str(mutant),"--scenario","all"],
                cwd=ROOT,capture_output=True,text=True,timeout=65)
            combined=(r.stdout+"\n"+r.stderr)
            behavior_failed='Exception in thread "main" java.lang.AssertionError' in combined
            killed=(r.returncode!=0 and behavior_failed
                    and "error: " not in combined and "CalledProcessError" in combined)
            results.append({"mutation":name,"exit":r.returncode,"behavior_failure":behavior_failed,
                            "killed":killed,"tail":combined[-650:]})
            print(("PASS" if killed else "FAIL")+" negative_control "+name,flush=True)
        if args.out:
            args.out.mkdir(parents=True,exist_ok=True)
            (args.out/"RESULTS.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    passed=sum(x["killed"] for x in results)
    print(f"EDIT_BINDING_NEGATIVE_CONTROLS {passed}/{len(results)}")
    return 0 if passed==len(results) else 1
if __name__=="__main__":raise SystemExit(main())