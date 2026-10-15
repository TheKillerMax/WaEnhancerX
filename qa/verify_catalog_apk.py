#!/usr/bin/env python3
"""Check the catalog against a compiled APK resource table, not source XML.

Requires Android Build Tools aapt2. Reads the embedded catalog and runs a read-only
resource dump. Missing catalog strings/default text fail (exit 1); malformed input,
unsupported dump output or unavailable tools fail (exit 2). Does not install the
APK, verify its signature, test Application.onCreate or certify Xposed hooks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

CATALOG = 'assets/preference_catalog.json'
MAX_CATALOG = 1024 * 1024
MAX_APK = 256 * 1024 * 1024
NAME = re.compile(r'[a-z][a-z0-9_]*\Z')
RESOURCE = re.compile(r'^\s+resource (0x[0-9a-fA-F]{8}) ([^\s/]+)/([^\s]+)(?:\s.*)?$')
PACKAGE = re.compile(r'^Package name=(\S+) id=([0-9a-fA-F]+)$')
VALUE = re.compile(r'^\s{6}\(([^)]*)\) (.+)$')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON property: ' + key)
        result[key] = value
    return result


def required_strings(raw: bytes) -> list[str]:
    if len(raw) > MAX_CATALOG:
        raise ValueError('Catalog exceeds input bound')
    groups = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(groups, list) or not groups or len(groups) > 1024:
        raise ValueError('Catalog must be a nonempty bounded group array')
    result = {}
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('Malformed catalog group')
        for field in ('id', 'tabId'):
            if not isinstance(group.get(field), str) or not NAME.fullmatch(group[field]):
                raise ValueError('Invalid catalog ' + field)
        keys = group.get('keys')
        if not isinstance(keys, list) or not keys or len(keys) > 4096:
            raise ValueError('Invalid catalog keys')
        for key in keys:
            if not isinstance(key, str) or not NAME.fullmatch(key):
                raise ValueError('Invalid catalog key')
            for suffix in ('title', 'desc'):
                result['feat_' + key + '_' + suffix] = None
        result['sec_' + group['id']] = None
        result['catalog_tab_' + group['tabId']] = None
    return sorted(result)


def parse_dump(text: str, package_name: str) -> dict[str, dict[str, str]]:
    """Accept aapt2's binary table output; fail on conflicting entries/IDs.

    The checker deliberately requires direct nonempty default string values for
    catalog labels. Indirect references or other output formats require review,
    not a guessed pass. Foreign-package entries never satisfy the requirement.
    """
    if not text.startswith('Binary APK\n'):
        raise ValueError('Expected aapt2 binary APK resource dump')
    packages = []
    package = None
    current = None
    result = {}
    seen_ids = {}
    for line in text.splitlines()[1:]:
        match = PACKAGE.fullmatch(line)
        if match:
            package = match.group(1)
            if package in packages:
                raise ValueError('Duplicate resource package')
            packages.append(package)
            current = None
            continue
        match = RESOURCE.fullmatch(line)
        if match:
            current = None
            if package != package_name:
                continue
            rid, kind, name = match.groups()
            identity = kind + '/' + name
            if rid in seen_ids and seen_ids[rid] != identity:
                raise ValueError('Conflicting resource ID')
            seen_ids[rid] = identity
            if kind == 'string':
                if name in result:
                    raise ValueError('Duplicate compiled string name')
                current = result[name] = {}
            continue
        if line.lstrip().startswith(('resource ', 'type ')):
            if line.lstrip().startswith('resource '):
                raise ValueError('Unrecognized aapt2 resource entry')
            current = None
            continue
        match = VALUE.fullmatch(line)
        if match and current is not None:
            config, value = match.groups()
            if config in current:
                raise ValueError('Duplicate string configuration')
            current[config] = value
    if package_name not in packages or not result:
        raise ValueError('Target package has no parsed compiled strings')
    return result


def assess(required: list[str], table: dict[str, dict[str, str]]) -> dict:
    missing = [name for name in required if name not in table]
    no_default = [name for name in required if name in table and not (
        table[name].get('', '').startswith('"') and
        table[name].get('', '').endswith('"') and
        table[name].get('', '')[1:-1].strip())]
    return {'required_count': len(required), 'present_count': len(required) - len(missing),
            'missing': missing, 'invalid_or_missing_default': no_default,
            'passed': not missing and not no_default}


def inspect(apk: Path, aapt2: str, package_name: str, expected_sha256: str | None = None) -> dict:
    if not apk.is_file() or apk.stat().st_size > MAX_APK:
        raise ValueError('Missing or oversized APK')
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise ValueError('APK SHA-256 does not match the expected artifact')
    with zipfile.ZipFile(apk) as archive:
        for name, limit in ((CATALOG, MAX_CATALOG), ('resources.arsc', 128 * 1024 * 1024)):
            entries = [entry for entry in archive.infolist() if entry.filename == name]
            if len(entries) != 1 or entries[0].file_size > limit:
                raise ValueError('Missing, duplicate or oversized APK entry: ' + name)
        with archive.open(CATALOG) as stream:
            required = required_strings(stream.read(MAX_CATALOG + 1))
    tool = shutil.which(aapt2)
    if tool is None:
        raise FileNotFoundError('aapt2 is required; source XML is not a substitute')
    proc = subprocess.run([tool, 'dump', 'resources', str(apk)], capture_output=True,
                          text=True, encoding='utf-8', timeout=120)
    if proc.returncode != 0:
        raise RuntimeError('aapt2 resource inspection failed: ' + proc.stderr[:1000])
    report = assess(required, parse_dump(proc.stdout, package_name))
    report.update({'apk': apk.name, 'sha256': digest, 'package': package_name,
                   'scope': 'compiled resource presence/default text; not Android startup or LSPosed'})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--aapt2', default='aapt2')
    parser.add_argument('--package', default='com.waenhancer')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    try:
        report = inspect(args.apk, args.aapt2, args.package, args.sha256)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(json.dumps({'passed': False, 'infrastructure_error': str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
