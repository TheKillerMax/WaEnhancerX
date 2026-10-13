#!/usr/bin/env python3
"""Read-only inventory of WaEnhancerX feature catalog and direct source references.

This is a PRE-FLIGHT, NOT a functionality/compatibility test. A key present in
hook code does not prove that the method was hooked or that it works in a host
APK. An absent direct literal does not prove that a feature is broken because
preferences can be transported through constants, dynamic lookup or the private
:licensing module. Never treat this output as an entitlement/license audit.

Usage: python3 qa/feature_contract_inventory.py [--root .] [--json|--markdown]
No APKs are read and no files are modified.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FEATURE = re.compile(r'FeatureItem\(\s*"([^"]+)"\s*,\s*"((?:\\.|[^"\\])*)"')
SCHEMA = re.compile(
    r'add\(entries,\s*"([^"]+)",\s*Type\.([A-Z_]+),\s*'
    r'Sensitivity\.([A-Z_]+),\s*Store\.([A-Z_]+)\)'
)
ALIAS = re.compile(r'"([^"]+)"\s+to\s+"([^"]+)"')


def inventory(root: Path) -> dict:
    java_root = root / 'app/src/main/java/com/waenhancer'
    catalog_path = java_root / 'config/FeatureCatalog.kt'
    schema_path = java_root / 'config/PreferenceSchema.java'
    codec_path = java_root / 'core/preferences/SettingsBackupCodec.kt'
    catalog = catalog_path.read_text(encoding='utf-8')
    schema = schema_path.read_text(encoding='utf-8')
    codec = codec_path.read_text(encoding='utf-8')
    features = [(m.group(1), m.group(2).replace('\\"', '"'),
                 catalog.count('\n', 0, m.start()) + 1) for m in FEATURE.finditer(catalog)]
    keys = [key for key, _, _ in features]
    if not features or len(set(keys)) != len(keys):
        raise ValueError('Empty catalog or duplicate feature keys')
    definitions = [(m.group(1), m.group(2), m.group(3), m.group(4))
                   for m in SCHEMA.finditer(schema)]
    schema_map = {k: {'type': t, 'sensitivity': s, 'store': st}
                  for k, t, s, st in definitions}
    if not schema_map or len(schema_map) != len(definitions):
        raise ValueError('Empty schema or duplicate preference definitions')
    aliases = dict(ALIAS.findall(codec))

    # Exact Java/Kotlin double-quoted literals; avoid substring matches on
    # similarly named keys. Count only Xposed module source, not UI strings.
    hook_files: list[tuple[str, str]] = []
    for path in (java_root / 'xposed').rglob('*'):
        if path.is_file() and path.suffix in ('.java', '.kt'):
            hook_files.append((path.relative_to(root).as_posix(),
                               path.read_text(encoding='utf-8', errors='replace')))

    rows = []
    for key, label, line in features:
        search = '"' + key + '"'
        runtime = [path for path, source in hook_files if search in source]
        entry = schema_map.get(key)
        legacy = aliases.get(key)
        legacy_entry = schema_map.get(legacy) if legacy else None
        rows.append({
            'key': key,
            'label': label,
            'catalog_line': line,
            'schema_type': entry['type'] if entry else None,
            'schema_store': entry['store'] if entry else None,
            'runtime_direct_refs': runtime,
            'legacy_alias': legacy,
            'alias_schema_type': legacy_entry['type'] if legacy_entry else None,
            'flags': (["NOT_IN_SCHEMA"] if not entry else []) +
                     (["NO_DIRECT_XPOSED_LITERAL"] if not runtime else []),
        })
    return {
        'schema_version': 1,
        'catalog_count': len(rows),
        'schema_key_count': len(schema_map),
        'not_in_schema': sum('NOT_IN_SCHEMA' in r['flags'] for r in rows),
        'without_direct_xposed_literal': sum('NO_DIRECT_XPOSED_LITERAL' in r['flags'] for r in rows),
        'features': rows,
        'limitations': (
            'Static source reference inventory only. A present key does not prove a hook is installed; '
            'an absent literal does not prove a feature is broken. Private licensing code, dynamic '
            'preference names, DexKit method resolution, and LSPosed device behavior are not tested.'
        )
    }


def markdown(report: dict) -> str:
    s = [
        '# WaEnhancerX feature contract source inventory',
        '',
        f"- Catalog features: **{report['catalog_count']}**",
        f"- Schema entries: **{report['schema_key_count']}**",
        f"- Catalog keys absent from schema: **{report['not_in_schema']}**",
        f"- Catalog keys without direct Xposed source literals: **{report['without_direct_xposed_literal']}**",
        '',
        'The counts below are **review flags**, not demonstrated runtime failures.',
        '',
        '| UI key | Type | Xposed source references | Legacy alias | Flags |',
        '|---|---|---:|---|---|',
    ]
    for row in report['features']:
        s.append('| ' + ' | '.join((
            '`' + row['key'] + '`',
            row['schema_type'] or '—',
            str(len(row['runtime_direct_refs'])),
            ('`' + row['legacy_alias'] + '`') if row['legacy_alias'] else '—',
            ', '.join(row['flags']) if row['flags'] else '—'
        )) + ' |')
    s.extend(['', '**Limitations:** ' + report['limitations'], ''])
    return '\n'.join(s)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument('--json', action='store_true')
    fmt.add_argument('--markdown', action='store_true')
    args = parser.parse_args()
    result = inventory(args.root)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.markdown:
        print(markdown(result))
    else:
        print(f"Features {result['catalog_count']}; schema {result['schema_key_count']}; "
              f"unregistered {result['not_in_schema']}; "
              f"no direct Xposed literal {result['without_direct_xposed_literal']}")
        print(result['limitations'])


if __name__ == '__main__':
    main()
