#!/usr/bin/env python3
"""Portable exact-fragment A/B validation; no Android/WhatsApp acceptance claim."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
RELATIVE = Path("app/src/main/java/com/waenhancer/xposed/features/conversation/MessageDeviceSourceHook.java")

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def extract_block(text, marker, start_at=0):
    start = text.index(marker, start_at)
    opened = text.index("{",start)
    depth = 1
    end = opened + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end], [text[:start].count("\n")+1,text[:end].count("\n")+1]

def fragments(raw):
    text = raw.decode("utf-8")
    pieces=[]; intervals=[]
    for i,line in enumerate(text.splitlines(keepends=True),1):
        if re.search(r"private static (?:final String (?:PRIMARY_DEVICE_EMOJI|LINKED_DEVICE_EMOJI|FIELD_DEVICE_(?:SUFFIX|ROW_BINDING|CLICK_LISTENER|GUARD|MSG_ID|ORIGINAL_TEXT|RENDERED_TEXT))\b|volatile Field sDevice(?:ListenerInfo|OnClickListener)Field\b)",line):
            pieces.append(line); intervals.append([i,i])
    for name in ["getDeviceEmojiSuffix","bindDeviceSourceUi","attachClickToast","stripDeviceEmoji","unannotatedText","renderDeviceSourceText","clearDeviceSourceTarget","readDeviceSourceClickListener"]:
        matches = list(re.finditer(r"^    private (?:static )?[^\n]*\b"+name+r"\(",text,re.M))
        if not matches:
            if name in ("readDeviceSourceClickListener", "stripDeviceEmoji", "unannotatedText", "renderDeviceSourceText", "clearDeviceSourceTarget"): continue
            raise RuntimeError("Missing method "+name)
        for match in matches:
            # Use the whole declaration line: overloaded methods share the
            # truncated prefix matched by the name-only search.
            declaration=text[match.start():text.find("\n",match.start())]
            part, interval=extract_block(text,declaration);pieces.append(part);intervals.append(interval)
    for marker in ["    private static final class DeviceSourceRowBinding", "    private final class DeviceSourceClickListener", "    private static final class DeviceSourceClickListener"]:
        if marker in text:
            part,interval=extract_block(text,marker);pieces.append(part);intervals.append(interval)
    return "\n".join(pieces),intervals

def execute(label, source, output, release):
    raw=source.read_bytes()
    body,intervals=fragments(raw)
    template=(ROOT/"ListenerOwnershipProbe.java.template").read_text()
    generated=template.replace("/* EXACT_SOURCE_FRAGMENTS */",body)
    work=output/label;work.mkdir(parents=True,exist_ok=True)
    java_source=work/"ListenerOwnershipProbe.java";java_source.write_text(generated)
    java=shutil.which("java")
    javac=shutil.which("javac")
    if not java: raise RuntimeError("java is required")
    compiler=[javac] if javac else [java,"-m","jdk.compiler/com.sun.tools.javac.Main"]
    if release:
        # This Linux runtime may ship javac without lib/ct.sym. Use explicit
        # source/bytecode levels then, and keep the effective flags in receipts.
        has_symbols=(Path(java).resolve().parents[1]/"lib/ct.sym").exists()
        compiler += (["--release",str(release)] if has_symbols
                     else ["-source",str(release),"-target",str(release)])
    compile_command=compiler+[java_source.name]
    run_command=[java,"ListenerOwnershipProbe"]
    started=time.monotonic()
    compile_result=subprocess.run(compile_command,cwd=work,text=True,capture_output=True,timeout=60)
    (work/"compile.stdout.txt").write_text(compile_result.stdout)
    (work/"compile.stderr.txt").write_text(compile_result.stderr)
    if compile_result.returncode: raise RuntimeError(f"{label}: compilation failure is not a negative detection\n{compile_result.stderr}")
    result=subprocess.run(run_command,cwd=work,text=True,capture_output=True,timeout=30)
    (work/"run.stdout.txt").write_text(result.stdout);(work/"run.stderr.txt").write_text(result.stderr)
    if result.returncode: raise RuntimeError(f"{label}: incomplete execution\n{result.stderr}")
    cases=[]
    for line in result.stdout.splitlines():
        if line.startswith("SUMMARY\t"): continue
        name,status,detail=line.split("\t",2)
        if status not in ("PASS","FAIL"): raise RuntimeError("Unexpected case status")
        cases.append({"name":name,"status":status,"detail":detail})
    if len(cases)!=26: raise RuntimeError(f"Expected26 completed cases, got {len(cases)}")
    return {"label":label,"source":str(source.resolve()),"source_sha256":digest(raw),
            "source_lines":len(raw.decode().splitlines()),"extracted_intervals":intervals,
            "generated_fixture":str(java_source.resolve()),"generated_fixture_sha256":digest(java_source.read_bytes()),
            "compile_command":compile_command,"compile_exit_code":compile_result.returncode,
            "run_command":run_command,"run_exit_code":result.returncode,
            "duration_seconds":time.monotonic()-started,"cases":cases,
            "pass_count":sum(c["status"]=="PASS" for c in cases),"fail_count":sum(c["status"]=="FAIL" for c in cases)}

def main():
    p=argparse.ArgumentParser();p.add_argument("--release",type=int);p.add_argument("--out",type=Path,default=ROOT/"ownership-results")
    p.add_argument("--source",type=Path);p.add_argument("--label",default="provided")
    p.add_argument("--allow-behavior-failures",action="store_true",help="Record a deliberate baseline/negative control without treating its expected assertions as candidate acceptance")
    args=p.parse_args()
    variants=[(args.label,args.source)] if args.source else [("candidate",WORKSPACE/RELATIVE)]
    results=[execute(label,source,args.out.resolve(),args.release) for label,source in variants]
    version=subprocess.run([shutil.which("java"),"-version"],text=True,capture_output=True)
    doc={"schema":"WAEX_LISTENER_OWNERSHIP_SOURCE_FRAGMENT_V1","created_utc":datetime.now(timezone.utc).isoformat(),
         "java":version.stderr.strip(),"release_flag":args.release,"fixture_provenance":"adapted from 2026-11-10 PR111 review",
         "scope":"Exact selected production methods and nested class; framework/Xposed objects are explicit strict doubles",
         "not_verified":["Full production class or APK build","Actual Android reflection accessibility","WhatsApp recycling and lifecycle reachability","All DeviceSource functionality","Current transcription collision"],
         "fault_injection":"Listener-info introspection shape can be hidden while the actual installed callback remains; this is a controlled reflection failure seam, not an observed vendor layout",
         "variants":results}
    dest=args.out.resolve()/"RESULTS.json";dest.write_text(json.dumps(doc,indent=2)+"\n")
    for r in results: print(r["label"],r["pass_count"],"PASS",r["fail_count"],"FAIL")
    print(dest)
    if args.source:
        if not args.allow_behavior_failures and any(r["fail_count"] for r in results): sys.exit(1)
    elif any(r["fail_count"] for r in results):
        sys.exit(1)

if __name__=="__main__":main()
