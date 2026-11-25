#!/usr/bin/env python3
"""Run runtime-reporting regressions with the qualified Kotlin 2.0.20/JDK21 compiler closure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from runtime_profile_toolchain.toolchain import prepare, verify_after_build

ROOT = Path(__file__).resolve().parents[1]
UID_MUTANTS = ['foreign-process-uid-admitted', 'foreign-package-profile-admitted',
               'same-profile-context-uid-admitted', 'missing-package-row-admitted',
               'pid-list-globbing', 'manager-pid-not-verified',
               'timestamp-after-command', 'partial-output-promoted']


def run_gate(command, stream, env, timeout):
    """Close a gate's whole Linux process group before its evidence is hashed."""
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                               stderr=subprocess.STDOUT, start_new_session=True)
    code = None
    try:
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = 'infrastructure_timeout'
    finally:
        # A gate can also time out an inner compiler and exit before that compiler.
        # Its new session contains only this gate's descendants, never sibling jobs.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # The last descendant can exit between the probe and signal.
            process.wait(timeout=5)
            if code == 0:
                code = 'infrastructure_descendant_leak'
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, default=os.environ.get('JAVA_HOME'))
    parser.add_argument('--toolchain-cache', type=Path)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--sdk-jars', type=Path)
    args = parser.parse_args()
    if args.java_home is None:
        parser.error('A preinstalled JDK21 is required')
    out = args.out.resolve();out.mkdir(parents=True, exist_ok=False)
    tool = out/'toolchain';tool.mkdir()
    launcher, env, receipt = prepare(tool, args.java_home, args.toolchain_cache)
    env['KOTLINC'] = str(launcher)
    env['KOTLIN_HOME'] = str(launcher.parents[1])
    env['PATH'] = str(launcher.parent)+os.pathsep+env['PATH']
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUTF8'] = '1'
    profile = ['qa/android_runtime_profile_test.py', '--out', str(out/'profile'),
               '--maven-repo', str(out/'maven-cache')]
    if args.deps:
        profile += ['--deps', str(args.deps.resolve())]
    if args.sdk_jars:
        profile += ['--sdk-jars', str(args.sdk_jars.resolve())]
    gates = [
        ('runtime-evidence', ['qa/test_runtime_diagnostics.py']),
        ('queue', ['qa/test_runtime_report_queue.py', '--out', str(out/'queue')]),
        ('catalogue', ['qa/test_startup_hook_reporting.py', '--out', str(out/'catalogue')]),
        ('injection-io', ['qa/test_injection_io_runtime.py', '--out', str(out/'injection-io')]),
        ('preference-telemetry', ['qa/test_preference_sync_runtime.py', '--out', str(out/'preference-telemetry')]),
        ('startup', ['qa/test_startup_reconciliation.py']),
        ('bridge', ['qa/test_bridge_contract.py']),
        ('observation-coordination', ['qa/test_runtime_observation_clock.py']),
        ('derived-evidence', ['qa/test_provider_derived_keys.py']),
        ('framework-profile', profile),
        ('injection-negative', ['qa/mutate_injection_io.py', '--out', str(out/'injection-negative')]),
        ('preference-negative', ['qa/mutate_preference_sync.py', '--out', str(out/'preference-negative')]),
        ('identity-negative', ['qa/mutate_runtime_evidence.py', '--out', str(out/'identity-negative'),
                               '--only', *UID_MUTANTS]),
    ]
    results = []
    closed = False
    try:
        for name, arguments in gates:
            command = [sys.executable, *arguments]
            log = out/(name+'.log');start=time.monotonic()
            with log.open('w', encoding='utf-8') as stream:
                code = run_gate(command, stream, env, timeout=900)
            record = {'gate': name, 'command': command, 'exit': code,
                      'seconds': round(time.monotonic()-start, 3),
                      'driver_sha256': hashlib.sha256((ROOT/arguments[0]).read_bytes()).hexdigest(),
                      'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
            results.append(record)
            (out/'gates.json').write_bytes((json.dumps(results, indent=2)+'\n').encode())
            print(json.dumps(record), flush=True)
    finally:
        verify_after_build(launcher, receipt)
        closed = True
        (out/'toolchain-closure.json').write_bytes((json.dumps({
            'compiler_and_jdk_unchanged': closed, 'lock_sha256': receipt['lock_sha256'],
            'commit': os.environ.get('GITHUB_SHA'), 'gate_count': len(results),
        }, indent=2)+'\n').encode())
    if not closed or len(results) != len(gates) or any(row['exit'] != 0 for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
