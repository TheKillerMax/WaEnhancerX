#!/usr/bin/env python3
"""Read-only static audit of literal SharedPreferences calls against WAEX schema.

This is a review inventory, not a compiler/type-checker: dynamic keys, helper
methods, generic map writes and private licensing files require separate checks.
Only direct literal get*/put*/isEnabled calls are enumerated. The source may
have intentional legacy fallback reads; only incompatible literal *writes*
are highlighted as possible storage corruption. No APK or network is needed.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE_BY_METHOD = {
    'getBoolean': 'BOOLEAN', 'putBoolean': 'BOOLEAN', 'isEnabled': 'BOOLEAN',
    'getString': 'STRING', 'putString': 'STRING',
    'getStringSet': 'STRING_SET', 'putStringSet': 'STRING_SET',
    'getInt': 'INT', 'putInt': 'INT',
    'getLong': 'LONG', 'putLong': 'LONG',
    'getFloat': 'FLOAT', 'putFloat': 'FLOAT',
}
DECLARATION = re.compile(r'add\(entries,\s*"([^"\n]+)",\s*Type\.([A-Z_]+),')
CALL = re.compile(r'(?<![\w])(' + '|'.join(map(re.escape, TYPE_BY_METHOD))
                  + r')\s*\(\s*"([^"\n]+)"')


def without_comments(text: str) -> str:
    """Replace // and /* */ comments with spaces while preserving line numbers.

    Java/Kotlin string and char literals are preserved so literal-key calls can
    be found. This does not parse interpolated or dynamically generated keys.
    """
    out = list(text)
    state = 'code'
    i = 0
    while i < len(text):
        c = text[i]
        next_char = text[i+1] if i+1 < len(text) else ''
        if state == 'code':
            if c == '/' and next_char == '/':
                out[i] = out[i+1] = ' '
                i += 2; state = 'line_comment'; continue
            if c == '/' and next_char == '*':
                out[i] = out[i+1] = ' '
                i += 2; state = 'block_comment'; continue
            if c == '"': state = 'double'
            elif c == "'": state = 'single'
        elif state == 'line_comment':
            if c == '\n': state = 'code'
            else: out[i] = ' '
        elif state == 'block_comment':
            if c == '*' and next_char == '/':
                out[i] = out[i+1] = ' '
                i += 2; state = 'code'; continue
            if c != '\n': out[i] = ' '
        elif state in ('double', 'single'):
            if c == '\\':
                i += 2; continue
            if c == ('"' if state == 'double' else "'"):
                state = 'code'
        i += 1
    return ''.join(out)


def analyse(schema_source: str, sources: dict[str, str]) -> dict:
    schema = dict(DECLARATION.findall(without_comments(schema_source)))
    if not schema:
        raise ValueError('No preference schema entries found')
    counts = {'matched_literals': 0, 'known_literals': 0, 'unknown_literals': 0}
    mismatched_reads, mismatched_writes = [], []
    for filename in sorted(sources):
        source = without_comments(sources[filename])
        for match in CALL.finditer(source):
            method, key = match.groups()
            expected = TYPE_BY_METHOD[method]
            actual = schema.get(key)
            counts['matched_literals'] += 1
            if actual is None:
                counts['unknown_literals'] += 1
                continue
            counts['known_literals'] += 1
            if expected == actual:
                continue
            record = {'file': filename, 'line': source.count('\n', 0, match.start())+1,
                      'key': key, 'method': method, 'access_type': expected,
                      'schema_type': actual}
            if method.startswith('put'):
                mismatched_writes.append(record)
            else:
                mismatched_reads.append(record)
    return {'schema_keys': len(schema), 'counts': counts,
            'mismatched_writes': mismatched_writes,
            'mismatched_reads': mismatched_reads,
            'disclaimer': ('Static literal calls only. Reads may have guarded legacy '
                           'fallback paths; dynamically constructed keys and private '
                           'licensing module are not checked. No hook runtime proof.')}


def scan(root: Path) -> dict:
    src = root / 'app/src/main/java/com/waenhancer'
    schema_path = src / 'config/PreferenceSchema.java'
    schema = schema_path.read_text(encoding='utf-8')
    contents = {}
    for path in sorted(src.rglob('*')):
        if path.suffix not in ('.kt', '.java') or path == schema_path:
            continue
        contents[str(path.relative_to(root))] = path.read_text(encoding='utf-8')
    return analyse(schema, contents)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--json', action='store_true')
    p.add_argument('--fail-on-writes', action='store_true',
                   help='Reject schema-mismatched literal writes (opt-in strict mode)')
    args = p.parse_args()
    try:
        report = scan(args.root)
    except (OSError, ValueError) as exc:
        print('Preference audit failed:', exc)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Reviewed {report['counts']['matched_literals']} literal preference accesses; "
              f"{len(report['mismatched_writes'])} incompatible writes, "
              f"{len(report['mismatched_reads'])} incompatible/legacy reads")
        for group in ('mismatched_writes', 'mismatched_reads'):
            for item in report[group]:
                print(f"{group}: {item['file']}:{item['line']} "
                      f"{item['method']}({item['key']!r}): "
                      f"{item['access_type']} vs {item['schema_type']}")
        print(report['disclaimer'])
    return 1 if args.fail_on_writes and report['mismatched_writes'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
