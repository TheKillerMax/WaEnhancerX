#!/usr/bin/env python3
"""Read actual catalog metadata; never substitute a historical feature list.

Supports the legacy inline catalog and the key-only JSON asset used by the
localized catalog. Mirrors canonicalGroupOverrides/filter/distinctBy ordering.
Default resources are required; this is source QA, not Android resource linking.
"""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

INLINE = re.compile(r'FeatureItem\(\s*"([^"\n]+)"\s*,\s*"((?:\\.|[^"\\])*)"')
NAME = re.compile(r'[a-z][a-z0-9_]*\Z')

def string_resources(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for file in sorted((root / 'app/src/main/res/values').glob('*.xml')):
        for node in ET.parse(file).getroot().findall('string'):
            name = node.get('name')
            if not name or name in result:
                raise ValueError(f'Missing or duplicate string resource: {name}')
            result[name] = ''.join(node.itertext()).replace(r"\'", "'").replace(r'\"', '"')
    return result

def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON property: {key}')
        result[key] = value
    return result

def catalog_features(root: Path) -> list[dict]:
    source_path = root / 'app/src/main/java/com/waenhancer/config/FeatureCatalog.kt'
    source = source_path.read_text(encoding='utf-8')
    asset_match = re.search(r'private const val ASSET_NAME\s*=\s*"([^"\n]+)"', source)
    if asset_match is None:
        rows = [{'key': m[1], 'label': m[2].replace(r'\"', '"'),
                 'catalog_line': source.count('\n', 0, m.start()) + 1,
                 'catalog_source': source_path.relative_to(root).as_posix()}
                for m in INLINE.finditer(source)]
        if not rows or len({row['key'] for row in rows}) != len(rows):
            raise ValueError('Empty catalog or duplicate feature keys')
        return rows
    name = asset_match[1]
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('Catalog asset must be a plain filename')
    asset = root / 'app/src/main/assets' / name
    groups = json.loads(asset.read_text(encoding='utf-8'), object_pairs_hook=_object)
    if not isinstance(groups, list) or not groups:
        raise ValueError('Catalog asset must contain nonempty groups')
    # Do not silently invent precedence when production uses an unfamiliar form.
    match = re.search(r'private val canonicalGroupOverrides\s*=\s*mapOf\((.*?)\n\s*\)', source, re.S)
    if (match is None or '.distinctBy { it.key }' not in source
            or 'canonicalGroupOverrides[item.key]?.let { it == item.groupId } ?: true' not in source
            or '.flatMap { it.items() }' not in source):
        raise ValueError('Unsupported catalog canonical routing contract')
    pairs = re.findall(r'"([^"\n]+)"\s+to\s+"([^"\n]+)"', match[1])
    remainder = re.sub(r'"([^"\n]+)"\s+to\s+"([^"\n]+)"|[\s,]', '', match[1])
    if remainder or len(dict(pairs)) != len(pairs):
        raise ValueError('Unsupported or duplicate canonical route')
    overrides = dict(pairs)
    resources = string_resources(root)
    placements = []
    seen_groups = set()
    def identifier(value):
        return isinstance(value, str) and NAME.fullmatch(value) is not None
    for group in groups:
        if not isinstance(group, dict) or not identifier(group.get('id')) or group['id'] in seen_groups:
            raise ValueError('Invalid or duplicate catalog group')
        seen_groups.add(group['id'])
        if type(group.get('tabIndex')) is not int or not identifier(group.get('tabId')):
            raise ValueError('Invalid catalog destination')
        if group.get('subTabId') is not None and not identifier(group['subTabId']):
            raise ValueError('Invalid catalog subtab')
        keys = group.get('keys')
        if not isinstance(keys, list) or not keys or not all(identifier(k) for k in keys) or len(set(keys)) != len(keys):
            raise ValueError('Empty, invalid or duplicate keys within a catalog group')
        pro = group.get('proKeys', [])
        if not isinstance(pro, list) or not all(identifier(k) for k in pro) or not set(pro) <= set(keys):
            raise ValueError('Pro keys must belong to their catalog group')
        required = [f"sec_{group['id']}", f"catalog_tab_{group['tabId']}"]
        required += [f'feat_{k}_{suffix}' for k in keys for suffix in ('title', 'desc')]
        missing = [key for key in required if not resources.get(key, '').strip()]
        if missing:
            raise ValueError('Missing/empty default catalog resources: ' + ', '.join(missing))
        for key in keys:
            placements.append({'key': key, 'label': resources[f'feat_{key}_title'],
                               'catalog_line': None, 'catalog_source': asset.relative_to(root).as_posix(),
                               'group_id': group['id'], 'tab_index': group['tabIndex'],
                               'sub_tab_id': group.get('subTabId'), 'tab_id': group['tabId'],
                               'is_pro': key in pro})
    for key, group_id in overrides.items():
        if not any(p['key'] == key and p['group_id'] == group_id for p in placements):
            raise ValueError(f'Canonical route has no placement: {key} -> {group_id}')
    selected = {}
    for row in placements:
        key = row['key']
        if key not in overrides or overrides[key] == row['group_id']:
            selected.setdefault(key, row)
    if not selected:
        raise ValueError('Empty canonical catalog')
    return list(selected.values())
