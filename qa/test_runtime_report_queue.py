#!/usr/bin/env python3
"""Execute the complete bounded report dispatcher; no Android or device benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('app/src/main/java/com/waenhancer/xposed/core/RuntimeReportDispatcher.java')
MUTANTS = [
    ('release-bypass', 'if (!released || draining || pending.isEmpty()) return;',
     'if (draining || pending.isEmpty()) return;', 'startup reports ran before lifecycle release'),
    ('duplicate-drain', 'if (!released || draining || pending.isEmpty()) return;',
     'if (!released || pending.isEmpty()) return;', 'repeated release scheduled duplicate drains'),
    ('stale-order', 'pending.remove(kind);', '/* retain stale insertion position */',
     'deferred reports lost latest state or inventory order'),
    ('catalogue-order', 'if (kind != Kind.HOOKS) {', 'if (true) {',
     'catalogue replacement moved pending inventory behind READY'),
    ('silent-rejection', 'reportFailure(rejected);', '/* suppress rejected worker */',
     'rejected worker was not surfaced'),
]


def execute(out):
    original = (ROOT / SOURCE).read_text(encoding='utf-8')
    fixture = ROOT / 'qa/TestRuntimeReportDispatcher.java'
    rows = []
    for label, before, after, expected in [('candidate', None, None, None), *MUTANTS]:
        source = original
        if before is not None:
            if source.count(before) != 1:
                raise AssertionError('Mutation anchor changed: ' + label)
            source = source.replace(before, after)
        work = out / label
        work.mkdir(parents=True)
        implementation = work / 'RuntimeReportDispatcher.java'
        implementation.write_text(source, encoding='utf-8')
        compile_result = subprocess.run(['javac', '--release', '17', '-d', str(work),
            str(implementation), str(fixture)], text=True, capture_output=True, timeout=30)
        (work / 'compile.log').write_text(compile_result.stdout + compile_result.stderr, encoding='utf-8')
        if compile_result.returncode:
            raise RuntimeError('Compilation failed, not a valid negative control: ' + label)
        result = subprocess.run(['java', '-cp', str(work),
            'com.waenhancer.xposed.core.TestRuntimeReportDispatcher'],
            text=True, capture_output=True, timeout=20)
        output = result.stdout + result.stderr
        (work / 'runtime.log').write_text(output, encoding='utf-8')
        accepted = result.returncode == 0 if expected is None else (
            result.returncode != 0 and 'AssertionError: ' + expected in output)
        rows.append({'label': label, 'accepted': accepted, 'exit': result.returncode,
                     'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                     'output': output})
        print(('PASS ' if accepted else 'FAIL ') + label + ': ' + output.strip())
        if not accepted:
            raise AssertionError('Queue contract did not produce expected behavior: ' + label)
    (out / 'result.json').write_text(json.dumps({'cases': rows,
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'scope': 'Complete Java dispatcher, explicit task/Executor substitutes; no Binder or Android'}, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        execute(args.out)
    else:
        with tempfile.TemporaryDirectory(prefix='waex-runtime-queue-') as folder:
            execute(Path(folder))


if __name__ == '__main__':
    main()
