#!/usr/bin/env python3
"""Compile and execute the complete production bounded queue; no Android/Binder claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(out):
    source = ROOT / 'app/src/main/java/com/waenhancer/xposed/core/RuntimeReportDispatcher.java'
    fixture = ROOT / 'qa/TestRuntimeReportDispatcher.java'
    out.mkdir(parents=True, exist_ok=True)
    compile_result = subprocess.run(['javac', '--release', '17', '-d', str(out), str(source), str(fixture)],
                                    text=True, capture_output=True, timeout=60)
    (out / 'compile.log').write_text(compile_result.stdout + compile_result.stderr, encoding='utf-8')
    if compile_result.returncode:
        raise RuntimeError('INFRASTRUCTURE_FAILURE: queue compile; ' + str(out / 'compile.log'))
    print('COMPILE_OK: complete production RuntimeReportDispatcher', flush=True)
    result = subprocess.run(['java', '-cp', str(out), 'com.waenhancer.xposed.core.TestRuntimeReportDispatcher'],
                            text=True, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    (out / 'runtime.log').write_text(output, encoding='utf-8')
    (out / 'result.json').write_text(json.dumps({
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'compile_exit': 0, 'runtime_exit': result.returncode, 'output': output,
        'scope': 'complete production queue, manual Executor and controlled blocking tasks; no Binder benchmark',
    }, indent=2) + '\n', encoding='utf-8')
    print(output, end='', flush=True)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        return run(args.out)
    with tempfile.TemporaryDirectory(prefix='waex-runtime-queue-') as directory:
        return run(Path(directory))


if __name__ == '__main__':
    raise SystemExit(main())
