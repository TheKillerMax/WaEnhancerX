#!/usr/bin/env python3
"""Compile real WAEX PID/UID classifier source with synthetic, user-separated processes.

JVM contract regression only: this is not an Android root/LSPosed/injection execution.
The intentionally broken same-name fallback must compile and fail the same oracle.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--kotlinc', default=shutil.which('kotlinc'))
    ap.add_argument('--java', default=shutil.which('java'))
    a = ap.parse_args()
    if not a.kotlinc or not a.java:
        raise RuntimeError('Real Kotlin compiler and Java runtime are required; no test-only fallback')

    root, out = a.root.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    java = root / 'app/src/main/java/com/waenhancer/utils'
    paths = [java / 'XposedRuntimeInspector.kt', java / 'InjectionEvidence.kt',
             root / 'qa/fixtures/RuntimeProfilePidChecks.kt']
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(p)
    source_sha = {str(p.relative_to(root)): digest(p) for p in paths}

    # SystemClock is the only Android symbol used by these real production sources.
    # Its deterministic value does not decide any PID, UID or boot classification.
    clock = out / 'Clock.kt'
    clock.write_text('''package android.os
object SystemClock { @JvmStatic fun elapsedRealtime(): Long = 1000L }
''', encoding='utf-8')

    def compile_sources(label: str, inspector: Path):
        jar = out / (label + '.jar')
        command = [a.kotlinc, '-jvm-target', '17', str(inspector),
                   str(paths[1]), str(paths[2]), str(clock),
                   '-include-runtime', '-d', str(jar)]
        started = time.monotonic()
        built = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (out / (label + '-compile.log')).write_text(built.stdout + built.stderr, encoding='utf-8')
        if built.returncode:
            raise RuntimeError(f'{label} Kotlin compilation failed: {built.stderr[-4000:]}')
        run = subprocess.run([a.java, '-jar', str(jar)], capture_output=True, text=True, timeout=30)
        (out / (label + '-run.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
        return jar, run, time.monotonic() - started

    candidate_jar, candidate, candidate_time = compile_sources('candidate', paths[0])
    match = re.search(r'PROFILE_PID_CASES=(\d+);FAILURES=0', candidate.stdout)
    if candidate.returncode != 0 or not match:
        raise AssertionError('Current PID/UID contract failed: ' + (candidate.stdout + candidate.stderr)[-4000:])
    cases = int(match.group(1))

    original = paths[0].read_text(encoding='utf-8')
    expected = '''return runningPidsByUid[packageName]?.get(expectedUid)
            ?: if (exhaustive) emptySet() else null'''
    if original.count(expected) != 1:
        raise AssertionError('UID-qualified lookup signature changed; negative control requires review')
    mutated = original.replace(expected, 'return pidsFor(packageName)')
    mutant_path = out / 'XposedRuntimeInspector-mutant.kt'
    mutant_path.write_text(mutated, encoding='utf-8')
    mutant_jar, mutant, mutant_time = compile_sources('mutant', mutant_path)
    if mutant.returncode == 0 or 'expected=' not in (mutant.stdout + mutant.stderr):
        raise AssertionError('Broken same-name PID fallback was not rejected by the independent oracle')

    result = {
        'status': 'PASS', 'cases': cases, 'failures': 0,
        'negative_control': 'PASS: mutant compiled; JUnit-free JVM oracle rejected wrong-user PID',
        'candidate_sha256': digest(candidate_jar),
        'mutant_sha256': digest(mutant_jar),
        'source_sha256': source_sha,
        'candidate_seconds': round(candidate_time, 2),
        'mutant_seconds': round(mutant_time, 2),
        'limits': 'Synthetic JVM parser/decision checks; not Android process ownership, root, LSPosed or WhatsApp runtime acceptance'
    }
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PASS: ' + json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
