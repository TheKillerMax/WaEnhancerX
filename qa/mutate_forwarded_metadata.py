#!/usr/bin/env python3
"""Require compiled behavioral rejection of unsafe forwarding changes.

Compile errors, unavailable tools, timeouts, and replacements that do not occur
are infrastructure failures. This runs the full production hook with explicit
Android/Xposed/DexKit substitutes, not an Android or WhatsApp process.
"""
from pathlib import Path
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/com/waenhancer/xposed/features/privacy/HideForwardedTagHook.kt'
CASES = [
    ('legacy_overrides_explicit_disable',
     'if (prefs.contains("hide_forwarded_tag")) prefs.getBoolean("hide_forwarded_tag", false)',
     'if (prefs.contains("hide_forwarded_tag")) (prefs.getBoolean("hide_forwarded_tag", false) || prefs.getBoolean("hidetag", false))'),
    ('origin_erased', 'updated.put("forward_score", 0)',
     'updated.put("forward_score", 0); updated.put("forward_origin", 0)'),
    ('unrelated_table_changed', 'if (table == "message_forwarded")', 'if (true)'),
    ('negative_score_changed', 'score is Int && score > 0', 'score is Int'),
    ('caller_values_mutated', 'val updated = ContentValues(values)', 'val updated = values'),
    ('missing_score_invented', 'if (score is Int && score > 0)', 'if (values != null)'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_text(encoding='utf-8')

    def run(case):
        name, before, after = case
        assert source.count(before) == 1, f'Inert or ambiguous mutation: {name}'
        changed = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='waex-forward-mutant-') as directory:
            candidate = Path(directory) / 'HideForwardedTagHook.kt'
            candidate.write_text(changed, encoding='utf-8')
            result = subprocess.run(
                ['python3', str(ROOT / 'qa/test_forwarded_metadata_scope.py'), '--source', str(candidate)],
                capture_output=True, text=True, timeout=180)
        log = result.stdout + result.stderr
        compiled = 'COMPILE_OK:' in result.stdout
        detected = result.returncode != 0 and compiled and 'java.lang.AssertionError: ASSERTION|' in log
        row = {'name': name, 'returncode': result.returncode, 'compiled': compiled,
               'detected': detected, 'source_sha256': hashlib.sha256(changed.encode()).hexdigest()}
        (args.out / (name + '.log')).write_text(log, encoding='utf-8')
        print(json.dumps(row), flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(run, CASES))
    (args.out / 'summary.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    assert all(row['detected'] for row in rows), 'A mutation was not rejected by compiled behavior'
    print(f'PASS: {len(rows)} compiled behavioral controls; no Android/WhatsApp runtime claim')


if __name__ == '__main__':
    main()
