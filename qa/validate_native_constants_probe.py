#!/usr/bin/env python3
"""Strict host validation for the isolated waexdiag constant probe; no ADB side effects."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile

PACKAGE = 'org.lab.waex.qa.nativeconstants'
COMPONENT = PACKAGE + '/.NativeConstantsInstrumentation'
SERIAL = 'emulator-5580'
SOURCE_REVISION = '9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d'
SOURCE_SHA256 = '96647f2fb72535da9a01c49d176d2ed868f93794a172c032a5afc92ea67b5756'
CMAKE_SHA256 = 'fed223aeac6d9efa008b04313e2e7a3dbe983c64becd53d5318f0093d875f7ef'
CONTRACT_SHA256 = '8b041fd2e053d87da39a76ad3a55f3077f5ff6441ce346fa66c8cc2811faba9f'
SCOPE = 'WAEXDIAG_CONSTANTS_ONLY_NO_COMMANDS_ROOT_OR_OTHER_LIBRARIES'
ELF_ENTRY = 'lib/x86_64/libwaexdiag.so'
CONTRACT_ENTRY = 'assets/expected_constants.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def contract(path=None):
    path = path or Path(__file__).parent / 'native_constants_probe/expected_constants.json'
    data = Path(path).read_bytes()
    require(digest(data) == CONTRACT_SHA256, 'Contract file identity changed')
    value = strict_json(data.decode('utf-8'))
    require(value['source_revision'] == SOURCE_REVISION and value['source_sha256'] == SOURCE_SHA256,
            'Contract source identity changed')
    return value


def source_inventory():
    base = Path(__file__).parent
    names = ('build_native_constants_probe.py', 'run_native_constants_probe.py',
             'validate_native_constants_probe.py', 'test_native_constants_probe.py',
             'NATIVE_CONSTANTS_PROBE.md', 'native_constants_probe/AndroidManifest.xml',
             'native_constants_probe/NativeDiagPaths.java',
             'native_constants_probe/NativeConstantsInstrumentation.java',
             'native_constants_probe/expected_constants.json')
    return {name: {'bytes': (base / name).stat().st_size,
                   'sha256': digest((base / name).read_bytes())} for name in names}


def inspect_apk(path, apk_sha256, elf_sha256):
    require(re.fullmatch('[0-9a-f]{64}', apk_sha256) and re.fullmatch('[0-9a-f]{64}', elf_sha256),
            'Invalid pinned APK/ELF hash')
    path = Path(path)
    require(0 < path.stat().st_size <= 8 * 1024**2, 'Unexpected APK size')
    data = path.read_bytes()
    require(digest(data) == apk_sha256, 'APK SHA256 mismatch')
    with zipfile.ZipFile(path) as zipped:
        entries = zipped.infolist()
        names = [entry.filename for entry in entries]
        require(len(names) == len(set(names)) and len(names) < 64, 'Duplicate/excessive APK entries')
        require(sum(entry.file_size for entry in entries) <= 8 * 1024**2, 'APK expanded size')
        for entry in entries:
            name = PurePosixPath(entry.filename)
            require(not name.is_absolute() and '..' not in name.parts and '\\' not in entry.filename,
                    'Invalid APK member path')
        require([name for name in names if name.startswith('lib/')] == [ELF_ENTRY], 'Unexpected native libraries')
        require([name for name in names if re.fullmatch(r'classes\d*\.dex', name)] == ['classes.dex'],
                'Unexpected DEX entries')
        require([name for name in names if name.startswith('assets/')] == [CONTRACT_ENTRY],
                'Unexpected asset entries')
        require('AndroidManifest.xml' in names and zipped.testzip() is None, 'APK integrity')
        require(digest(zipped.read(CONTRACT_ENTRY)) == CONTRACT_SHA256, 'Bundled oracle changed')
        elf = zipped.getinfo(ELF_ENTRY)
        require(elf.compress_type == zipfile.ZIP_STORED and 0 < elf.file_size < 1024**2,
                'Native library must be stored and bounded')
        require(digest(zipped.read(ELF_ENTRY)) == elf_sha256, 'Bundled ELF SHA256 mismatch')
        offset = elf.header_offset
        require(data[offset:offset+4] == b'PK\x03\x04', 'Invalid local ZIP header')
        filename_bytes, extra_bytes = struct.unpack_from('<HH', data, offset + 26)
        position = offset + 30 + filename_bytes + extra_bytes
        require(position % 16384 == 0, 'Native payload is not aligned to 16384 bytes')
        return {'apk_sha256': apk_sha256, 'apk_bytes': len(data), 'elf_sha256': elf_sha256,
                'elf_bytes': elf.file_size, 'elf_data_offset': position, 'stored_alignment': 16384,
                'native_entries': [ELF_ENTRY], 'contract_sha256': CONTRACT_SHA256}


def validate_output(text, *, nonce, api, page_size, apk_sha256, elf_sha256):
    require(len(text.encode('utf-8')) <= 65536, 'Instrumentation output too large')
    require(re.fullmatch('[0-9a-f]{32}', nonce), 'Invalid requested nonce')
    require(type(api) is int and 24 <= api <= 37 and type(page_size) is int
            and page_size in (4096, 16384), 'Invalid expected guest identity')
    require(not re.search(r'INSTRUMENTATION_(?:FAILED|ABORTED)|waex_native_error|'
                          r'INSTRUMENTATION_RESULT:\s*(?:shortMsg|longMsg|Error)=', text),
            'Instrumentation reported a failure')
    lines = [line.strip() for line in text.splitlines()]
    require([line for line in lines if line.startswith('INSTRUMENTATION_CODE:')]
            == ['INSTRUMENTATION_CODE: -1'], 'Expected exactly one successful instrumentation finish')
    prefix = 'INSTRUMENTATION_RESULT: waex_native_receipt='
    receipts = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    require(len(receipts) == 1, 'Expected exactly one receipt')
    value = strict_json(receipts[0])
    fixed = {'schema': 'WAEXDIAG_JNI_CONSTANTS_V2', 'scope': SCOPE, 'package': PACKAGE,
             'run_nonce': nonce, 'sdk': api, 'application_page_size_bytes': page_size,
             'own_apk_sha256': apk_sha256, 'bundled_elf_sha256': elf_sha256,
             'source_revision': SOURCE_REVISION, 'source_sha256': SOURCE_SHA256,
             'cmake_sha256': CMAKE_SHA256, 'contract_sha256': CONTRACT_SHA256,
             'load_library_returned': True, 'process_is_64bit': True, 'jni_calls': 14, 'strings_checked': 38}
    other = {'release', 'hardware', 'supported_abis', 'uid', 'pid', 'return_values', 'duration_ms'}
    require(type(value) is dict and set(value) == set(fixed) | other, 'Receipt schema fields changed')
    for key, expected in fixed.items():
        require(type(value[key]) is type(expected) and value[key] == expected, 'Receipt identity: ' + key)
    require(isinstance(value['release'], str) and 0 < len(value['release']) < 64, 'Invalid release')
    require(value['hardware'] in ('ranchu', 'goldfish'), 'Not the expected emulator hardware')
    require(type(value['supported_abis']) is list and value['supported_abis']
            and value['supported_abis'][0] == 'x86_64'
            and all(type(item) is str for item in value['supported_abis']), 'Unexpected guest ABIs')
    require(type(value['uid']) is int and value['uid'] >= 10000
            and type(value['pid']) is int and value['pid'] > 0, 'Invalid process identity')
    require(type(value['duration_ms']) is int and 0 <= value['duration_ms'] <= 60000, 'Invalid duration')
    expected_values = {name: item['value'] for name, item in contract()['methods'].items()}
    require(type(value['return_values']) is dict and value['return_values'] == expected_values,
            'JNI returned values differ from the complete frozen contract')
    return value
