#!/usr/bin/env python3
"""Read-only DEX field compatibility preflight for a specified host class.

Evidence is confined to declaration metadata in the supplied APK; it cannot
establish the meaning of obfuscated fields or execution of LSPosed hooks.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import zipfile
from pathlib import Path

DEX_NAME = re.compile(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex\Z')

class MalformedDex(ValueError):
    pass


def u16(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 2 > len(data):
        raise MalformedDex('Read past end of DEX (u16)')
    return struct.unpack_from('<H', data, pos)[0]


def u32(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise MalformedDex('Read past end of DEX (u32)')
    return struct.unpack_from('<I', data, pos)[0]


def table(data: bytes, size_offset: int, stride: int) -> tuple[int, int]:
    count, offset = u32(data, size_offset), u32(data, size_offset + 4)
    if count > 2_000_000 or offset > len(data) or count * stride > len(data) - offset:
        raise MalformedDex('Invalid DEX table offset/count')
    return count, offset


def uleb128(data: bytes, pos: int) -> tuple[int,int]:
    value = 0
    for shift in range(0, 35, 7):
        if pos >= len(data):
            raise MalformedDex('Truncated DEX string length')
        chunk = data[pos]
        pos += 1
        value |= (chunk & 0x7f) << shift
        if chunk < 0x80:
            return value, pos
    raise MalformedDex('Oversized DEX string length')


def declared_fields(dex: bytes, owner: str) -> list[dict] | None:
    if len(dex) < 112 or dex[:4] != b'dex\n' or u32(dex, 32) != len(dex):
        raise MalformedDex('Missing/invalid DEX header')
    sc, so = table(dex, 56, 4)
    strings = []
    for i in range(sc):
        start = u32(dex, so + 4*i)
        _, start = uleb128(dex, start)
        end = dex.find(b'\0', start)
        if end < 0:
            raise MalformedDex('Unterminated DEX string')
        strings.append(dex[start:end].decode('utf-8', 'replace'))
    tc, to = table(dex, 64, 4)
    types=[]
    for i in range(tc):
        idx=u32(dex, to+4*i)
        if idx>=sc: raise MalformedDex('Invalid type string index')
        types.append(strings[idx])
    cc, co = table(dex, 96, 32)
    classdata = None
    for i in range(cc):
        ci = u32(dex, co + 32*i)
        if ci >= tc:
            raise MalformedDex('Invalid class definition')
        if types[ci] == owner:
            if classdata is not None:
                raise MalformedDex('Duplicate class definition')
            classdata = u32(dex, co + 32*i + 24)
    if classdata is None:
        return None
    if classdata == 0:
        return []
    fc, fo = table(dex, 80, 8)
    cursor = classdata
    counts = []
    for _ in range(4):
        count, cursor = uleb128(dex, cursor)
        if count > 2_000_000: raise MalformedDex('Invalid encoded member count')
        counts.append(count)
    result = []
    for count in counts[:2]:
        field_index = 0
        for _ in range(count):
            delta, cursor = uleb128(dex, cursor)
            _, cursor = uleb128(dex, cursor)  # access_flags
            field_index += delta
            if field_index >= fc:
                raise MalformedDex('Class field index outside field_ids table')
            ci, ti, ni = struct.unpack_from('<HHI', dex, fo + 8*field_index)
            if ci >= tc or ti >= tc or ni >= sc:
                raise MalformedDex('Invalid DEX field ID')
            if types[ci] != owner:
                raise MalformedDex('Class owns unexpected field ID')
            result.append({'name': strings[ni], 'type': types[ti]})
    result.sort(key=lambda f: (f['name'], f['type']))
    return result


def inspect_apk(apk: Path, class_descriptor: str, expected_field: str) -> dict:
    if not class_descriptor.startswith('L') or not class_descriptor.endswith(';'):
        raise ValueError('Class must use DEX descriptor format, e.g. Lcom/whatsapp/Foo;')
    matches=[];scanned=0
    with zipfile.ZipFile(apk) as z:
        entries=[x for x in z.namelist() if DEX_NAME.fullmatch(x)]
        if not entries:
            raise MalformedDex('No classes*.dex in APK')
        for name in sorted(entries):
            scanned+=1
            result=declared_fields(z.read(name),class_descriptor)
            if result is not None:
                matches.append({'dex':name,'fields':result})
    fields=[f for match in matches for f in match['fields']]
    has=any(f['name']==expected_field for f in fields)
    return {'apk':apk.name,'class':class_descriptor,'expected_field':expected_field,
            'dex_count':scanned,'defined_in':[m['dex'] for m in matches],
            'field_count':len(fields),'expected_field_declared':has,
            'jid_typed_fields':[f for f in fields if 'Jid;' in f['type']],
            'status':'PRESENT' if has else ('MISSING_FIELD' if matches else 'MISSING_CLASS'),
            'scope':'DEX declared field names/types only, not receiver identity semantics or runtime hook success'}


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--class-descriptor',required=True)
    parser.add_argument('--expected-field',default='jid')
    parser.add_argument('--fail-on-missing', action='store_true')
    args=parser.parse_args(argv)
    try:
        out=inspect_apk(args.apk,args.class_descriptor,args.expected_field)
    except (OSError, zipfile.BadZipFile, MalformedDex, ValueError) as exc:
        print(json.dumps({'status':'ERROR','detail':str(exc)}));return 2
    print(json.dumps(out,indent=2))
    return 1 if args.fail_on_missing and not out['expected_field_declared'] else 0

if __name__=='__main__':raise SystemExit(main())
