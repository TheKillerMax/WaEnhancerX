#!/usr/bin/env python3
"""Compile complete production capture/store code; run its SQL with real SQLite.

Android, Binder, Xposed and native DexKit discovery are explicit doubles. This is
not an APK, device, or asynchronous WhatsApp deletion acceptance test.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = 'app/src/main/java/com/waenhancer'


def encode(value):
    if value is None:
        return 'n'
    if isinstance(value, int):
        return 'i' + str(value)
    return 's' + base64.b64encode(str(value).encode()).decode()


def decode(value):
    if value == 'n':
        return None
    if value.startswith('i'):
        return int(value[1:])
    assert value.startswith('s'), value
    return base64.b64decode(value[1:]).decode()


def bridge(path):
    # Autocommit allows the SQLiteOpenHelper double to provide the documented
    # Android BEGIN/COMMIT/ROLLBACK boundary around the production onUpgrade.
    db = sqlite3.connect(path, isolation_level=None)
    try:
        for line in sys.stdin:
            try:
                parts = line.rstrip('\n').split('\t')
                sql = base64.b64decode(parts[1]).decode()
                values = [decode(v) for v in parts[2:]]
                if parts[0] == 'f':
                    # Force an actual SQLite error on the unmodified production
                    # copy statement, then remove the fault so reopening can retry.
                    db.set_authorizer(lambda operation, table, *_: sqlite3.SQLITE_DENY
                                      if operation == sqlite3.SQLITE_INSERT and table == 'preserved_messages'
                                      else sqlite3.SQLITE_OK)
                try:
                    cursor = db.execute(sql, values)
                finally:
                    db.set_authorizer(None)
                columns = [c[0] for c in cursor.description or ()]
                rows = cursor.fetchall() if columns else []
                response = ['OK', str(cursor.lastrowid or 0), str(max(0, cursor.rowcount)),
                            str(len(columns)), str(len(rows))]
                response += [encode(c) for c in columns]
                response += [encode(c) for row in rows for c in row]
                if trace := os.environ.get('WAEX_SQL_TRACE'):
                    with open(trace, 'a') as output:
                        output.write(json.dumps({'database': str(Path(path).name), 'sql': sql,
                                                 'args': values, 'rows': rows}, ensure_ascii=False) + '\n')
                print('\t'.join(response), flush=True)
            except Exception as failure:
                if trace := os.environ.get('WAEX_SQL_TRACE'):
                    with open(trace, 'a') as output:
                        output.write(json.dumps({'database': str(Path(path).name), 'sql': sql,
                                                 'args': values, 'error': str(failure)}) + '\n')
                print('ERR\t' + base64.b64encode(str(failure).encode()).decode(), flush=True)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--scenario', default='all')
    parser.add_argument('--dexkit-jar', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    args = parser.parse_args()
    for tool in ('javac', 'kotlinc', 'java'):
        if not shutil.which(tool):
            raise SystemExit('Required tool unavailable: ' + tool)
    if args.dexkit_jar and not args.dexkit_jar.is_file():
        raise SystemExit('DexKit jar does not exist')
    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with tempfile.TemporaryDirectory(prefix='waex-preserved-') as temp:
        out = Path(temp)
        src = out / 'src'; src.mkdir()
        classes = out / 'classes'; classes.mkdir()
        fixtures = ROOT / 'qa/fixtures'
        doubles_path = fixtures / 'preserved_messages_android_doubles.py'
        doubles = runpy.run_path(str(doubles_path))
        for name, content in doubles['JAVA'].items():
            (src / name).write_text(content)
        for name, content in doubles['KOTLIN'].items():
            if args.dexkit_jar and name.startswith('DexKit'):
                continue
            (src / name).write_text(content)
        for relative in (
            'xposed/features/conversation/PreserveDeleteForMeHook.kt',
            'xposed/features/conversation/PreservedMessageSelection.kt',
            'xposed/core/db/PreservedMessageStore.kt',
            'utils/ContactIdentityPolicy.java',
        ):
            path = args.source_root / PRODUCTION / relative
            # Old main has no selection helper; its full hook/store can still be
            # compiled and exercised by the same negative-control scenarios.
            if not path.exists() and relative.endswith('PreservedMessageSelection.kt'):
                continue
            (src / path.name).write_bytes(path.read_bytes())
            hashes[str(path.relative_to(args.source_root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        fixture = fixtures / 'PreservedMessagesChecks.kt'
        (src / fixture.name).write_bytes(fixture.read_bytes())
        selector_fixture = fixtures / 'PreservedSelectorChecks.kt'
        if not args.dexkit_jar and selector_fixture.exists():
            (src / selector_fixture.name).write_bytes(selector_fixture.read_bytes())
            hashes[str(selector_fixture.relative_to(ROOT))] = hashlib.sha256(selector_fixture.read_bytes()).hexdigest()
        for path in (Path(__file__), doubles_path, fixture):
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        cp = str(classes) + (os.pathsep + str(args.dexkit_jar.resolve()) if args.dexkit_jar else '')
        subprocess.run(['javac', '-d', str(classes), *map(str, sorted(src.glob('*.java')))], check=True, timeout=60)
        subprocess.run(['kotlinc', '-nowarn', '-language-version', '2.0', '-jvm-target', '17',
                        '-cp', cp, *map(str, sorted(src.glob('*.kt'))), '-include-runtime',
                        '-d', str(out / 'checks.jar')], check=True, timeout=120)
        print('COMPILE_OK: complete production preserved hook/selection/store and real identity policy', flush=True)
        print('SOURCE_SHA256=' + json.dumps(hashes, sort_keys=True), flush=True)
        env = os.environ | {'WAEX_SQL_PYTHON': sys.executable, 'WAEX_SQL_BRIDGE': str(Path(__file__).resolve())}
        results = []
        if args.evidence_dir:
            (args.evidence_dir / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
        for scenario in args.scenario.split(','):
            if args.evidence_dir:
                trace = args.evidence_dir / (scenario + '-sqlite.jsonl')
                trace.write_text('')
                env['WAEX_SQL_TRACE'] = str(trace.resolve())
            result = subprocess.run(['java', '-cp', str(out / 'checks.jar') + os.pathsep + cp,
                            'com.waenhancer.xposed.features.conversation.PreservedMessagesChecksKt',
                            str(out / 'databases' / scenario), scenario], env=env, timeout=120,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print(result.stdout, end='', flush=True)
            results.append({'scenario': scenario, 'compiled': True, 'exit_code': result.returncode})
            if args.evidence_dir:
                (args.evidence_dir / (scenario + '.log')).write_text(result.stdout)
        if args.evidence_dir:
            (args.evidence_dir / 'scenario-results.json').write_text(json.dumps(results, indent=2) + '\n')
        if any(r['exit_code'] for r in results):
            raise SystemExit(1)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--sqlite-bridge':
        bridge(sys.argv[2])
    else:
        main()
