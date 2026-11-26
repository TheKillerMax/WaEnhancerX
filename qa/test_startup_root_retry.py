#!/usr/bin/env python3
"""Kotlin/JVM behavior of the real root cache and exact manager retry call.

Extracts the untouched root-cache region from UpdateDownloader and the single
hasRootAccess invocation from MainActivity. Only elapsedRealtime and the root
command are controlled boundaries. No Android, Compose lifecycle, su, licensing,
network, installation, or whole-APK build is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def need(value, message):
    if not value:
        raise RuntimeError(message)


def retry_effect(main_source):
    marker = 'LaunchedEffect(rootCheckAttempt)'
    need(main_source.count(marker) == 1, 'Expected one retry-keyed lifecycle effect')
    start = main_source.index('{', main_source.index(marker) + len(marker))
    depth = 0
    for end in range(start, len(main_source)):
        depth += (main_source[end] == '{') - (main_source[end] == '}')
        if depth == 0:
            return main_source[start:end + 1]
    raise RuntimeError('Unterminated retry lifecycle effect')


CLOCK = '''package android.os
object SystemClock {
    var nowMillis: Long = 1000L
    @JvmStatic fun elapsedRealtime(): Long = nowMillis
}
'''

SCAFFOLD = '''package com.waenhancer.update
object UpdateDownloader {
CACHE_SOURCE
    var harnessCalls = 0
    var harnessOutput: String? = null
    private fun runRootCommand(command: String): String? {
        check(command == "id")
        harnessCalls++
        return harnessOutput
    }
    fun resetHarness(output: String?) {
        cachedRootAccess = null
        lastRootCheckElapsed = 0L
        harnessCalls = 0
        harnessOutput = output
        android.os.SystemClock.nowMillis = 1000L
    }
}
'''

CHECKS = '''package checks
import com.waenhancer.update.UpdateDownloader
import android.os.SystemClock

fun managerCall(rootCheckAttempt: Int): Boolean = MAIN_CALL

fun main() {
    var cases = 0
    val failures = mutableListOf<String>()
    fun scenario(name: String, body: () -> Unit) {
        cases++
        try {
            body()
            println("PASS " + name)
        } catch (failure: Throwable) {
            failures.add(name + ": " + failure.toString())
            println("FAIL " + name)
        }
    }
    scenario("initial check preserves negative cache") {
        UpdateDownloader.resetHarness("uid=2000(shell)")
        check(!managerCall(0))
        check(UpdateDownloader.harnessCalls == 1)
        SystemClock.nowMillis = 2000L
        UpdateDownloader.harnessOutput = "uid=0(root)"
        check(!managerCall(0))
        check(UpdateDownloader.harnessCalls == 1)
    }
    scenario("explicit retry bypasses recent denial") {
        UpdateDownloader.resetHarness("uid=2000(shell)")
        check(!managerCall(0))
        SystemClock.nowMillis = 2000L
        UpdateDownloader.harnessOutput = "uid=0(root)"
        check(managerCall(1)) { "Retry must observe the newly granted root result" }
        check(UpdateDownloader.harnessCalls == 2) { "Retry must perform a new command" }
    }
    scenario("explicit retry observes revoked root") {
        UpdateDownloader.resetHarness("uid=0(root)")
        check(managerCall(0))
        SystemClock.nowMillis = 2000L
        UpdateDownloader.harnessOutput = "uid=2000(shell)"
        check(!managerCall(2)) { "Retry must observe the newly denied root result" }
        check(UpdateDownloader.harnessCalls == 2)
    }
    scenario("ordinary check preserves positive cache") {
        UpdateDownloader.resetHarness("uid=0(root)")
        check(managerCall(0))
        SystemClock.nowMillis = 2000L
        UpdateDownloader.harnessOutput = "uid=2000(shell)"
        check(managerCall(0))
        check(UpdateDownloader.harnessCalls == 1)
    }
    scenario("ordinary check refreshes at exact TTL boundary") {
        UpdateDownloader.resetHarness("uid=2000(shell)")
        check(!managerCall(0))
        SystemClock.nowMillis = 61000L
        UpdateDownloader.harnessOutput = "uid=0(root)"
        check(managerCall(0))
        check(UpdateDownloader.harnessCalls == 2)
    }
    scenario("retry command failure does not reuse cached grant") {
        UpdateDownloader.resetHarness("uid=0(root)")
        check(managerCall(0))
        SystemClock.nowMillis = 2000L
        UpdateDownloader.harnessOutput = null
        check(!managerCall(1)) { "A failed fresh probe must not claim root is available" }
        check(UpdateDownloader.harnessCalls == 2)
    }
    println("ROOT_RETRY_CASES=" + cases + ";FAILURES=" + failures.size)
    failures.forEach { println(it) }
    if (failures.isNotEmpty()) throw IllegalStateException("ROOT_RETRY_BEHAVIOR_FAILED")
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--main-source', type=Path)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--kotlin-home', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root / 'app/src/main/java/com/waenhancer'
    downloader = source / 'update/UpdateDownloader.kt'
    activity = args.main_source or source / 'app/MainActivity.kt'
    code = downloader.read_text(encoding='utf-8')
    main_source = activity.read_text(encoding='utf-8')
    begin = code.index('    @Volatile\n    private var cachedRootAccess: Boolean? = null')
    end = code.index('\n    fun downloadApk(', begin)
    cache_source = code[begin:end]
    need(cache_source.count('fun hasRootAccess(') == 1 and cache_source.count('runRootCommand("id")') == 1,
         'Unexpected cache extraction boundary')
    calls = re.findall(r'UpdateDownloader\.hasRootAccess\([^()]*\)', main_source)
    need(len(calls) == 1, 'Expected one exact MainActivity root invocation')
    effect = retry_effect(main_source)
    need(calls[0] in effect, 'Root invocation must belong to the retry lifecycle effect')
    need('if (initialRootResultProvided && rootCheckAttempt == 0) return@LaunchedEffect' in effect,
         'Initial startup handoff changed')
    need('onRetry = { rootCheckAttempt++ }' in main_source, 'Retry counter boundary changed')
    args.out.mkdir(parents=True, exist_ok=False)
    generated = args.out / 'generated'
    generated.mkdir()
    files = {'SystemClock.kt': CLOCK,
             'UpdateDownloader.kt': SCAFFOLD.replace('CACHE_SOURCE', cache_source),
             'RootRetryChecks.kt': CHECKS.replace('MAIN_CALL', calls[0])}
    for name, value in files.items():
        (generated / name).write_text(value, encoding='utf-8')
    compiler = args.kotlin_home / 'lib/kotlin-compiler.jar'
    stdlib = args.kotlin_home / 'lib/kotlin-stdlib.jar'
    need(args.java.is_file() and compiler.is_file() and stdlib.is_file(), 'Existing JDK/Kotlin runtime required')
    jar = args.out / 'checks.jar'
    commands = []

    def run(argv, label):
        done = subprocess.run(list(map(str, argv)), capture_output=True, timeout=90)
        (args.out / (label + '.stdout.log')).write_bytes(done.stdout)
        (args.out / (label + '.stderr.log')).write_bytes(done.stderr)
        commands.append({'argv': list(map(str, argv)), 'exit_code': done.returncode,
                         'stdout_sha256': hashlib.sha256(done.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(done.stderr).hexdigest()})
        return done

    compiled = run([args.java, '-cp', args.kotlin_home / 'lib/*',
                    'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-kotlin-home', args.kotlin_home,
                    '-language-version', '2.0', '-jvm-target', '17', '-include-runtime',
                    '-d', jar, *sorted(generated.glob('*.kt'))], 'compile')
    need(compiled.returncode == 0, 'Compilation failed; inspect retained compiler logs')
    behavior = run([args.java, '-ea', '-jar', jar], 'behavior')
    output = behavior.stdout.decode('utf-8', errors='strict')
    match = re.search(r'ROOT_RETRY_CASES=(\d+);FAILURES=(\d+)', output)
    need(match is not None and int(match[1]) == 6, 'Incomplete behavior report')
    report = {'schema': 'WAEX_STARTUP_ROOT_RETRY_BEHAVIOR_C03',
              'status': 'PASS_EXTRACTED_REAL_KOTLIN_BEHAVIOR' if behavior.returncode == 0 else 'FAIL_EXTRACTED_REAL_KOTLIN_BEHAVIOR',
              'unique_scenarios': int(match[1]), 'failures': int(match[2]),
              'main_invocation': calls[0], 'commands': commands,
              'source_pins': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (activity, downloader)},
              'cache_region_sha256': hashlib.sha256(cache_source.encode('utf-8')).hexdigest(),
              'retry_effect_sha256': hashlib.sha256(effect.encode('utf-8')).hexdigest(),
              'tool_pins': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.java, compiler, stdlib)},
              'android_or_su_executed': False, 'licensing_loaded_or_replaced': False,
              'compose_lifecycle_tested': False, 'whole_apk_built': False,
              'scope': 'Exact extracted cache body and exact activity invocation compiled on Kotlin/JVM; clock/root-command boundaries controlled.'}
    (args.out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(output, end='')
    return 0 if behavior.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
