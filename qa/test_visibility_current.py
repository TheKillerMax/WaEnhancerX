#!/usr/bin/env python3
"""Compile current local visibility contracts on real Android/Robolectric API 24/28/34.

Host discovery and Xposed dispatch are explicit controlled boundaries. No private
engine, real host injection, permission changes or device rendering is exercised.
All public API bytes are verified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("app/src/main/java/com/waenhancer")
SOURCES = [JAVA / p for p in (
    "xposed/core/BaseFeature.kt", "xposed/core/HookRegistrar.java",
    "xposed/core/ViewHookDispatcher.java", "xposed/utils/HookErrors.java",
    "xposed/utils/HostClassNames.java", "xposed/utils/HostResourceIds.java",
    "xposed/utils/ViewClassSelector.java",
    "xposed/features/customization/ChannelRecommendationsFilterHook.kt",
    "xposed/features/homescreen/ChatListCustomizationsHook.java")]
CHANNEL = SOURCES[-2]
CHAT = SOURCES[-1]
FIXTURES = ROOT / "qa/fixtures/visibility_current"
EXPECTED = 60

def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()

def run(command, log, *, accept_failure=False):
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run([str(x) for x in command], stdout=stream,
                                stderr=subprocess.STDOUT, timeout=180)
    if result.returncode and not accept_failure:
        raise RuntimeError(str(log) + ": " + log.read_text(encoding="utf-8", errors="replace")[-5000:])
    return result.returncode

def mutate(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Mutation anchor is not unique: " + old)
    return source.replace(old, new, 1)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, required=True)
    for name in ("deps", "sdk-jars", "dexkit-jar", "core-api-jar", "kotlin-home"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--mutations", action="store_true")
    a = p.parse_args()
    root, out = a.root.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for path, digest in ((a.dexkit_jar, "195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1"),
                         (a.core_api_jar, "d1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0")):
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError("Pinned API identity mismatch: " + str(path))
    kotlin = a.kotlin_home.resolve(strict=True)
    compiler = kotlin / "lib/kotlin-compiler.jar"
    stdlib = kotlin / "lib/kotlin-stdlib.jar"
    for item in (compiler, stdlib):
        if not item.is_file():
            raise RuntimeError("Incomplete Kotlin compiler distribution")
    java, javac = shutil.which("java"), shutil.which("javac")
    if not java or not javac:
        raise RuntimeError("JDK required")
    command = [java, "-Dkotlin.home=" + str(kotlin), "-cp", str(kotlin / "lib/*"),
               "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler", "-kotlin-home", str(kotlin)]
    run([*command, "-version"], out / "kotlin-version.log")
    run([java, "-version"], out / "java-version.log")
    dependencies = sorted(a.deps.resolve().glob("*.jar")) + [a.dexkit_jar.resolve(), a.core_api_jar.resolve(), stdlib]
    sdks = sorted(a.sdk_jars.resolve().glob("*.jar"))
    if len(sdks) != 3:
        raise RuntimeError("Expected the three supplied instrumented Android SDKs")
    android = next(p for p in dependencies if p.name == "android-all-14-robolectric-10818077.jar")
    production = os.pathsep.join(map(str, [android, a.dexkit_jar.resolve(), a.core_api_jar.resolve(), stdlib]))
    cp = os.pathsep.join(map(str, dependencies))
    fixtures = [FIXTURES / "AppearanceCurrentContractTest.java", FIXTURES / "ViewClassSelectorTest.java"]
    if sum(len(re.findall(r"@Test\b", f.read_text(encoding="utf-8"))) for f in fixtures) * 3 != EXPECTED:
        raise RuntimeError("Review changed test denominator")
    originals = {p: (root / p).read_bytes() for p in SOURCES}
    channel, chat = originals[CHANNEL].decode("utf-8"), originals[CHAT].decode("utf-8")
    variants = {"healthy": ({}, None)}
    if a.mutations:
        variants["channel-resize"] = ({CHANNEL: mutate(channel, "view.visibility = View.GONE",
            "view.visibility = View.GONE\n                view.layoutParams?.let { it.width=0; it.height=0; view.layoutParams=it }")},
            "channelHidesWithoutOverwritingHostLayout")
        variants["meta-switch"] = ({CHAT: mutate(chat, 'return isMetaAiDisabled() && prefs.getBoolean("metaai_block_chat", true);',
            'return prefs.getBoolean("metaai_block_chat", true);')}, "chatMasterOffDoesNotBlockConversation")
        variants["channel-rebind"] = ({CHANNEL: mutate(channel, "(flags and visibilityMask.inv()) or View.GONE", "flags")},
            "channelHostRebindPreservesOtherFlagBits")
    ids = sorted(set(re.findall(r"R\.string\.(\w+)", "\n".join(x.decode("utf-8") for x in originals.values()))))
    resource_ids = set()
    for path in (root / "app/src/main/res/values").glob("*.xml"):
        resource_ids.update(e.attrib["name"] for e in ET.parse(path).getroot() if e.tag == "string" and "name" in e.attrib)
    missing = set(ids) - resource_ids
    if missing:
        raise RuntimeError("Missing production string IDs: " + repr(sorted(missing)))
    records = []
    for name, (variant, expected_method) in variants.items():
        case = out / name
        stage, classes = case / "sources", case / "classes"
        classes.mkdir(parents=True)
        for path, data in originals.items():
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(variant[path].encode("utf-8") if path in variant else data)
        boundaries = runpy.run_path(str(FIXTURES / "boundaries.py"))["STUBS"]
        boundaries["com/waenhancer/app/R.java"] = "package com.waenhancer.app; public final class R { public static final class string {" + "".join("public static final int " + key + "=" + str(i+1) + ";" for i,key in enumerate(ids)) + "}}"
        adapters = []
        for rel, text in boundaries.items():
            target = stage / "boundaries" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            adapters.append(target)
        run([javac, "--release", "17", "-encoding", "UTF-8", "-cp", production, "-d", classes, *adapters], case/"compile-boundaries.log")
        run([*command, "-jvm-target", "17", "-cp", str(classes)+os.pathsep+production, "-d", classes,
             *[stage/p for p in SOURCES]], case/"compile-kotlin.log")
        run([javac, "--release", "17", "-encoding", "UTF-8", "-cp", str(classes)+os.pathsep+production,
             "-d", classes, *[stage/p for p in SOURCES if p.suffix==".java"]], case/"compile-java.log")
        run([javac, "--release", "17", "-encoding", "UTF-8", "-cp", str(classes)+os.pathsep+cp,
             "-d", classes, *fixtures], case/"compile-test.log")
        code = run([java, "-Xmx1g", "--add-opens=java.base/java.lang=ALL-UNNAMED",
                    "--add-opens=java.base/java.util=ALL-UNNAMED", "-Drobolectric.offline=true",
                    "-Drobolectric.dependency.dir="+str(a.sdk_jars.resolve()),
                    "-cp", str(classes)+os.pathsep+cp, "org.junit.runner.JUnitCore",
                    *["com.waenhancer.xposed.features.customization." + f.stem for f in fixtures]],
                   case/"junit.log", accept_failure=True)
        log = (case/"junit.log").read_text(encoding="utf-8", errors="replace")
        good = re.search(r"OK \((\d+) tests?\)", log)
        bad = re.search(r"Tests run: (\d+),\s+Failures: (\d+)", log)
        count = int(good[1]) if good else int(bad[1]) if bad else 0
        failures = int(bad[2]) if bad else 0
        assertions = len(re.findall(r"(?m)^java\.lang\.AssertionError(?::.*)?$", log))
        causal = len(re.findall(r"(?m)^\d+\) " + re.escape(expected_method) + r"(?:\[[^\]]+\])?\(",log)) if expected_method else 0
        accepted = count == EXPECTED and ((code == 0 and good is not None) if expected_method is None else
                   (code != 0 and failures == assertions and causal == 3 and failures >= 3))
        row = {"variant":name,"tests":count,"failures":failures,"assertions":assertions,
               "expected_method":expected_method,"causal_failures":causal,"accepted":accepted,
               "variant_sha256":{str(p):hashlib.sha256(variant[p].encode("utf-8") if p in variant else data).hexdigest() for p,data in originals.items()}}
        records.append(row)
        print(json.dumps(row), flush=True)
        if not accepted:
            print(log[-5000:])
            raise RuntimeError("Unexpected behavior for "+name)
    result = {"results":records,"accepted":True,"source_sha256":{str(p):sha(root/p) for p in SOURCES},
              "fixture_sha256":{str(p):sha(p) for p in (*fixtures,FIXTURES/"boundaries.py",Path(__file__))},
              "dependency_sha256":{str(p):sha(p) for p in dependencies},
              "sdk_sha256":{p.name:sha(p) for p in sdks},
              "compiler_sha256":sha(compiler),"scope":__doc__}
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__":
    main()
