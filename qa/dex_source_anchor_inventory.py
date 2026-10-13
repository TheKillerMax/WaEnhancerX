#!/usr/bin/env python3
"""Read-only source-driven DEX literal preflight for WAEX/WhatsApp compatibility.

Extract every *literal* addUsingString("...") from the current Java/Kotlin tree,
then look for exact/substring matches inside DEX string_ids of the supplied APK.
A found literal does NOT prove a DexKit method candidate or hook compatibility.
An absent literal only rules out this literal-based match in this exact APK.
Never upload the host APK or dump unrelated strings to public repositories.
"""
from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import re
import struct
import sys
import zipfile
import zlib
from pathlib import Path

DEX_NAME = re.compile(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex\Z")
LITERAL = re.compile(r'\baddUsingString\s*\(\s*"((?:\\.|[^"\\])*)"', re.MULTILINE)
MAX_DEX = 256 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_STRINGS = 4_000_000

class AuditError(Exception):
    pass


def source_anchors(src: Path):
    if not src.is_dir():
        raise AuditError("Source directory does not exist")
    result: dict[str, list[dict]] = {}
    for path in sorted(src.rglob('*')):
        if path.suffix not in ('.java', '.kt') or not path.is_file():
            continue
        code = path.read_text(encoding='utf-8')
        for match in LITERAL.finditer(code):
            try:
                literal = codecs.decode(match.group(1), 'unicode_escape')
                literal.encode('ascii')
            except (UnicodeError, ValueError):
                continue  # Non-ASCII/dynamic anchors need separate DexKit verification.
            line = code.count('\n', 0, match.start()) + 1
            result.setdefault(literal, []).append({
                'source': str(path.relative_to(src)).replace('\\', '/'), 'line': line})
    if not result:
        raise AuditError("No literal addUsingString matchers in source directory")
    return result


def uleb_end(data: bytes, offset: int) -> int:
    for i in range(5):
        if offset + i >= len(data):
            raise AuditError("Truncated DEX string length")
        if data[offset + i] < 128:
            return offset + i + 1
    raise AuditError("Invalid DEX ULEB128 length")


def scan_apk(apk: Path, literals: list[str]):
    if not apk.is_file() or apk.stat().st_size == 0:
        raise AuditError("APK missing or empty")
    needles = {text: text.encode('ascii') for text in literals}
    found = {text: [] for text in literals}
    try:
        with zipfile.ZipFile(apk) as archive:
            all_entries = archive.infolist()
            if len(all_entries) > MAX_ENTRIES or sum(e.file_size for e in all_entries) > MAX_TOTAL:
                raise AuditError("APK archive exceeds size/entry limits")
            dex_files = [e for e in all_entries if DEX_NAME.fullmatch(e.filename)]
            if not dex_files or not any(e.filename == 'classes.dex' for e in dex_files):
                raise AuditError("Missing primary classes.dex")
            if len({item.filename for item in dex_files}) != len(dex_files):
                raise AuditError("Duplicate DEX archive member")
            for item in dex_files:
                if item.file_size > MAX_DEX:
                    raise AuditError("DEX file exceeds size limit")
                dex = archive.read(item)  # zipfile verifies each DEX member CRC.
                if (len(dex) < 112 or dex[:4] != b'dex\n'
                        or dex[4:7] not in (b'035', b'037', b'038', b'039', b'040', b'041')
                        or dex[7] != 0):
                    raise AuditError("Invalid DEX header")
                if struct.unpack_from('<I', dex, 0x24)[0] not in (112, 120):
                    raise AuditError("Invalid DEX header size")
                if struct.unpack_from('<I', dex, 0x20)[0] != len(dex):
                    raise AuditError("DEX length mismatch")
                if hashlib.sha1(dex[32:]).digest() != dex[12:32]:
                    raise AuditError("DEX SHA-1 mismatch")
                if zlib.adler32(dex[12:]) != struct.unpack_from('<I', dex, 8)[0]:
                    raise AuditError("DEX Adler-32 mismatch")
                count, offset = struct.unpack_from('<II', dex, 0x38)
                if count > MAX_STRINGS or offset > len(dex) or count * 4 > len(dex) - offset:
                    raise AuditError("Invalid DEX string table")
                # Scan each DEX independently so reports list every dex file
                # containing the requested literal, not just the first hit.
                needed = dict(needles)
                for (string_offset,) in struct.iter_unpack('<I', memoryview(dex)[offset:offset+count*4]):
                    # Validate *all* strings even after every requested anchor
                    # is found; an early break would silently accept malformed
                    # later string IDs in an otherwise correctly hashed DEX.
                    if string_offset >= len(dex):
                        raise AuditError("Invalid DEX string-data offset")
                    begin = uleb_end(dex, string_offset)
                    end = dex.find(b'\0', begin, min(begin + 2*1024*1024, len(dex)))
                    if end < 0:
                        raise AuditError("Invalid/oversized DEX string-data item")
                    string_value = dex[begin:end]
                    for literal, needle in tuple(needed.items()):
                        if needle in string_value:
                            found[literal].append(item.filename)
                            del needed[literal]
    except (OSError, zipfile.BadZipFile, RuntimeError, struct.error, EOFError) as exc:
        raise AuditError(f"Malformed or unreadable APK: {type(exc).__name__}") from exc
    return sorted({e for locs in found.values() for e in locs}), found, len(dex_files)


def audit(apk: Path, source: Path):
    anchors = source_anchors(source)
    used_dex, found, dex_count = scan_apk(apk, sorted(anchors))
    entries = [{'literal': key, 'sites': anchors[key],
                'present': bool(found[key]), 'dex_files': found[key]}
               for key in sorted(anchors)]
    return {'apk_name': apk.name, 'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
            'dex_files_checked': dex_count, 'dex_files_with_matches': used_dex,
            'anchor_count': len(entries),
            'anchors_present': sum(e['present'] for e in entries),
            'anchors_missing': sum(not e['present'] for e in entries),
            'anchors': entries,
            'caveat': 'DEX string pool presence is not method resolution or LSPosed runtime validation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path('app/src/main/java'))
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Exit 3 for any absent literal')
    args = parser.parse_args(argv)
    try:
        report = audit(args.apk, args.source_root)
    except AuditError as exc:
        print(f'DEX source preflight failed: {exc}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f'{report["apk_name"]}: {report["anchors_present"]}/{report["anchor_count"]} '
              'source literal anchors found (NOT proof of functional hooks)')
        for item in report['anchors']:
            if not item['present']:
                locations=', '.join(f"{s['source']}:{s['line']}" for s in item['sites'])
                print(f'  ABSENT {item["literal"]} — {locations}')
        print(report['caveat'])
    return 3 if args.strict and report['anchors_missing'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
