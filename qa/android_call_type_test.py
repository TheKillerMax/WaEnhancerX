#!/usr/bin/env python3
"""Offline public call-owner/selector fixtures on Robolectric API 24/28/34.

Supply preverified dependency and instrumented SDK directories plus the pinned
DexKit 2.2.0 API JAR. This runner never resolves Maven or starts external calls.
The contract suite stands alone. Selector/all additionally require the dependent
controller focus and preserve all original PN/LID/continuation/cancellation cases.
Optional explicit APK paths add production fingerprint checks over file bytes;
no APK is downloaded, installed, loaded as classes, or executed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from localization_support import write_r

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("app/src/main/java/com/waenhancer")
FIRST = [BASE / p for p in (
    "utils/ContactIdentityPolicy.java", "utils/DisplayLocalePolicy.java", "utils/UiText.java",
    "xposed/utils/HookErrors.java", "xposed/core/devkit/DexNegativeLookupCache.java",
    "xposed/core/devkit/DexCacheManager.java", "xposed/core/devkit/DexSearchEngine.java")]
KOTLIN = [BASE / p for p in ("xposed/core/BaseFeature.kt", "xposed/core/db/PreservedMessageStore.kt",
    "utils/ContactNameResolver.kt")]
LIFECYCLE = [BASE / p for p in ("xposed/core/HookRegistrar.java", "xposed/core/ViewHookDispatcher.java")]
FIX = Path("qa/fixtures/call_type")
DOUBLES = [FIX / (p + ".java") for p in ("XC_MethodHook", "XposedBridge", "XposedHelpers")]
HOOKS = BASE / "xposed/features/privacy"
EXPECTED = {"contract": 36, "selector": 114, "all": 150}
DEXKIT_SHA256 = "195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(command, log, allow_failure=False):
    result = subprocess.run(list(map(str, command)), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=300)
    log.write_bytes(result.stdout)
    print(log.name, "exit=" + str(result.returncode), flush=True)
    if result.returncode and not allow_failure:
        print(result.stdout.decode("utf-8", errors="replace")[-12000:])
        raise RuntimeError("Command failed: " + str(command[0]))
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--sdk-jars", type=Path, required=True)
    parser.add_argument("--dexkit", type=Path, required=True)
    parser.add_argument("--suite", choices=tuple(EXPECTED), default="all")
    parser.add_argument("--personal-apk", type=Path, help="Optional inspected Personal base APK for fingerprint checks")
    parser.add_argument("--business-apk", type=Path, help="Optional inspected Business base APK; supply both APK paths")
    parser.add_argument("--allow-test-failure", action="store_true",
        help="Write failed JUnit evidence for a mutation driver; never mark a failed suite accepted")
    args = parser.parse_args()
    if (args.personal_apk is None) != (args.business_apk is None):
        parser.error("Fingerprint checks require both --personal-apk and --business-apk")
    profile_apks = [p.resolve() for p in (args.personal_apk, args.business_apk) if p is not None]
    if any(not p.is_file() for p in profile_apks):
        raise RuntimeError("Explicit fingerprint APK input is missing")
    profile_hashes = [digest(p) for p in profile_apks]
    root, out = args.source_root.resolve(), args.out.resolve()
    deps, sdks, dexkit = args.deps.resolve(), args.sdk_jars.resolve(), args.dexkit.resolve()
    if digest(dexkit) != DEXKIT_SHA256:
        raise RuntimeError("Pinned DexKit 2.2.0 API identity mismatch")
    selector = args.suite in ("selector", "all")
    tests = (["CallTypeContractTest"] if args.suite in ("contract", "all") else [])
    if selector:
        tests.append("CallTypeAndroidTest")
    hook_files = [HOOKS / "CallTypeHostProfile.java", HOOKS / "CallTypeHostContract.java"]
    if selector:
        hook_files.append(HOOKS / "CallTypeControllerHook.java")
    fixture_files = [FIX / (name + ".java") for name in tests] + [FIX / "CallTypeJUnit.java"]
    if profile_apks:
        fixture_files.append(FIX / "CallTypeProfileFileCheck.java")
    product_files = FIRST + hook_files + (KOTLIN + LIFECYCLE if selector else [])
    for path in product_files + DOUBLES + fixture_files:
        if not (root / path).is_file():
            raise RuntimeError("Selected suite requires source: " + str(path))
    declared = sum(len(re.findall(r"@Test\s+public void", (root / FIX / (n + ".java")).read_text())) for n in tests) * 3
    if declared != EXPECTED[args.suite]:
        raise RuntimeError("Fixture inventory differs from reviewed " + str(EXPECTED[args.suite]) + "-case gate")
    compiler = shutil.which("kotlinc")
    if not compiler:
        raise RuntimeError("Kotlin compiler distribution is required")
    lib = Path(compiler).resolve().parents[1] / "lib"
    stdlib = lib / "kotlin-stdlib.jar"
    if not stdlib.is_file() or os.environ.get("KOTLIN_RUNNER") or os.environ.get("KOTLIN_COMPILER"):
        raise RuntimeError("Use an unmodified Kotlin compiler distribution")
    compiler_command = [compiler]
    if os.name == "nt":
        compiler_command = ["java", "-Dkotlin.home=" + str(lib.parent), "-cp",
            os.pathsep.join(map(str, sorted(lib.glob("*.jar")))), "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler"]
    out.mkdir(parents=True, exist_ok=False)
    run([*compiler_command, "-version"], out / "compiler-version.log")
    identities = {}
    def checked(relative):
        p = root / relative
        identities[str(relative)] = digest(p)
        return p.read_text(encoding="utf-8")
    gradle, properties = checked("app/build.gradle.kts"), checked("gradle.properties")
    for pattern in (r'namespace\s*=\s*"com\.waenhancer\.app"', r'versionCode\s*=\s*configuredVersionCode',
                    r'versionName\s*=\s*project\.findProperty\("VERSION_NAME"\)', r'buildConfig\s*=\s*true'):
        if re.search(pattern, gradle) is None:
            raise RuntimeError("Generated BuildConfig source contract changed")
    codes = re.findall(r"(?m)^VERSION_CODE=(\d+)\s*$", properties)
    names = re.findall(r"(?m)^VERSION_NAME=([^\r\n]+)$", properties)
    if len(codes) != 1 or len(names) != 1 or not 0 < int(codes[0]) <= 2147483647 or not names[0].strip():
        raise RuntimeError("Expected one valid Gradle version code/name")
    main_hook = checked("app/src/main/java/com/waenhancer/xposed/MainHook.java")
    if not re.search(r"public\s+static\s+volatile\s+String\s+sModulePath\s*;", main_hook):
        raise RuntimeError("Review native module-path compile contract")
    generated = {
        "com/waenhancer/app/BuildConfig.java": "package com.waenhancer.app; public final class BuildConfig { public static final int VERSION_CODE="
            + codes[0] + "; public static final String VERSION_NAME=" + json.dumps(names[0].strip()) + "; }\n",
        "com/waenhancer/xposed/MainHook.java": "package com.waenhancer.xposed; public final class MainHook { public static volatile String sModulePath; }\n",
    }
    if selector:
        registry = checked("app/src/main/java/com/waenhancer/xposed/core/FeatureRegistry.java")
        registration = 'registerFeature(CallTypeControllerHook.class, "Privacy",\n                () -> prefs.getBoolean("call_type_controller", false),\n                () -> new CallTypeControllerHook(context, classLoader, prefs));'
        if registry.count(registration) != 1 or "((ScreenScopedFeature) feature).onScreenDisposed(activity);" not in registry:
            raise RuntimeError("Review current conditional registration and screen disposal contract")
        base = checked(BASE / "xposed/core/BaseFeature.kt")
        if "protected val privacy: PrivacyPrefs by lazy { PrivacyPrefs.of(context, prefs) }" not in base:
            raise RuntimeError("Review lazy privacy-service boundary")
        generated["com/waenhancer/xposed/core/privacy/PrivacyPrefs.java"] = (
            "package com.waenhancer.xposed.core.privacy; public final class PrivacyPrefs { "
            "public static PrivacyPrefs of(android.content.Context c, android.content.SharedPreferences p) { "
            'throw new AssertionError("Privacy service is outside call selector fixture"); } }\n')
        # Public registry call-site descriptor only. No private implementation is loaded.
        generated["com/waenhancer/hooking/ScreenScopedFeature.java"] = (
            "package com.waenhancer.hooking; public interface ScreenScopedFeature { "
            "void onScreenDisposed(android.app.Activity activity); }\n")
    for name in ("NonNull", "Nullable", "VisibleForTesting"):
        generated["androidx/annotation/" + name + ".java"] = "package androidx.annotation; public @interface " + name + " {}\n"
    stage, classes = out / "sources", out / "classes"
    classes.mkdir()
    staged = {}
    for relative in product_files + DOUBLES + fixture_files:
        dest = stage / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, dest)
        staged[relative] = dest
        identities[str(relative)] = digest(root / relative)
    compiled_generated = []
    for relative, content in generated.items():
        dest = stage / "generated" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
        compiled_generated.append(dest)
        identities["generated/" + relative] = digest(dest)
    r_source, _ = write_r(root, stage / "generated")
    identities["generated/R.java"] = digest(r_source)
    identities["qa/android_call_type_test.py"] = digest(Path(__file__).resolve())
    identities["qa/localization_support.py"] = digest(ROOT / "qa/localization_support.py")
    jars = sorted(deps.glob("*.jar"))
    if not any(re.fullmatch(r"kotlin-stdlib-[0-9].*\.jar", p.name) for p in jars):
        jars.append(stdlib)
    jars.append(dexkit)
    android = deps / "android-all-14-robolectric-10818077.jar"
    if not android.is_file() or not sdks.is_dir():
        raise RuntimeError("Pinned compilation API or offline Android SDK JAR directory missing")
    prod_cp = os.pathsep.join(map(str, (classes, android, stdlib, dexkit)))
    cp = str(classes) + os.pathsep + os.pathsep.join(map(str, jars))
    run(["javac", "--release", "17", "-cp", prod_cp, "-d", classes,
         *compiled_generated, r_source, *[staged[p] for p in DOUBLES + FIRST]], out / "javac-dependencies.log")
    if selector:
        run([*compiler_command, "-jvm-target", "17", "-classpath", prod_cp, "-d", classes,
             *[staged[p] for p in KOTLIN + LIFECYCLE]], out / "kotlinc-production.log")
        run(["javac", "--release", "17", "-cp", prod_cp, "-d", classes,
             *[staged[p] for p in LIFECYCLE]], out / "javac-lifecycle.log")
    run(["javac", "--release", "17", "-cp", prod_cp, "-d", classes,
         *[staged[p] for p in hook_files]], out / "javac-call-contract.log")
    run(["javac", "--release", "17", "-cp", cp, "-d", classes,
         *[staged[p] for p in fixture_files]], out / "javac-tests.log")
    opens = ["java.base/java.lang", "java.base/java.util", "java.base/java.io", "java.base/java.net",
        "java.base/java.security", "java.base/java.text", "java.base/jdk.internal.access",
        "java.desktop/java.awt.font", "jdk.compiler/com.sun.tools.javac.api"]
    exit_code = run(["java", *["--add-opens=" + p + "=ALL-UNNAMED" for p in opens],
        "-Drobolectric.offline=true", "-Drobolectric.dependency.dir=" + str(sdks), "-cp", cp,
        "qa.CallTypeJUnit", *["com.waenhancer.xposed.features.privacy." + n for n in tests]],
        out / "junit.log", allow_failure=True)
    summaries = re.findall(r"(?m)^WAEX_TEST_SUMMARY (.+)$", (out / "junit.log").read_text(encoding="utf-8"))
    if len(summaries) != 1:
        raise RuntimeError("Missing or duplicate JUnit summary")
    result = json.loads(summaries[0])
    result.update(source_root=str(root), suite=args.suite, expected_tests=EXPECTED[args.suite],
        junit_exit_code=exit_code, source_sha256=identities)
    result["accepted"] = (exit_code == 0 and result["tests"] == EXPECTED[args.suite]
        and result["failures"] == 0 and result["skipped"] == 0)
    file_check = {"requested": bool(profile_apks), "status": "NOT_REQUESTED", "checks": 0, "accepted": False}
    if profile_apks:
        file_exit = run(["java", "-cp", cp,
            "com.waenhancer.xposed.features.privacy.CallTypeProfileFileCheck", *profile_apks,
            out / "profile-files"], out / "profile-files.log", allow_failure=True)
        rows = [json.loads(line) for line in (out / "profile-files.log").read_text(encoding="utf-8").splitlines()
                if line.startswith("{")]
        summaries = [row for row in rows if row.get("status") == "PASS"]
        unchanged = profile_hashes == [digest(p) for p in profile_apks]
        accepted = file_exit == 0 and len(summaries) == 1 and summaries[0].get("checks") == 15 and unchanged
        file_check.update(status="PASS" if accepted else "FAIL", exit_code=file_exit, accepted=accepted,
            checks=summaries[0]["checks"] if len(summaries) == 1 else 0,
            input_sha256=profile_hashes, inputs_unchanged=unchanged, observations=rows)
        result["accepted"] = result["accepted"] and accepted
    result["profile_file_check"] = file_check
    result["limits"] = ("Real Android 24/28/34 APIs, complete public host contract and selected controller/dependencies; "
        "Xposed, host classes, ScreenScopedFeature descriptor and unused lazy privacy service are explicit fixtures. "
        "No target WhatsApp class execution, runtime host binding, private module, APK build, external phone/WhatsApp call or device change.")
    (out / "dependency-sha256.json").write_text(json.dumps({p.name: digest(p) for p in jars + sorted(sdks.glob("*.jar"))}, indent=2) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "source_sha256"}, indent=2))
    if not args.allow_test_failure and not result["accepted"]:
        raise RuntimeError("Selected call contract suite did not pass")

if __name__ == "__main__":
    main()

