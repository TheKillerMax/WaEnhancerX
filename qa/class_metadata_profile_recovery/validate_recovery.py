#!/usr/bin/env python3
"""Strict consumer for a new identity receipt plus the unchanged four workload markers."""
import hashlib
import json
import re
import struct

from class_metadata_profile_recovery.recovery_contract import CANONICAL, TARGETS, VARIANTS, RUNTIME_VARIANTS, minor, require

CLASSES = ('com.waenhancer.xposed.core.wa.WaJid',
           'com.waenhancer.xposed.features.privacy.HideReceiptsHook')
IDENTITY_PREFIX = 'WAEX_ART_PROFILE_IDENTITY_V1|'
FIELDS = {'schema', 'status', 'nonce', 'phase_nonce', 'variant', 'target', 'sdk_int',
          'sdk_int_full_field_read', 'sdk_int_full', 'sdk_full_major', 'sdk_full_minor',
          'sdk_full_helpers_called', 'expected_minor', 'legacy_minor_zero_from_profile_only',
          'is_64_bit', 'elf_class', 'elf_machine', 'elf_endian', 'elf_header_hex', 'elf_header_sha256',
          'executable', 'application_page_size_bytes', 'page_size_method', 'uid', 'pid', 'hardware',
          'fingerprint', 'boot_id_before', 'boot_id_after', 'driver_path', 'driver_sha256',
          'driver_bytes', 'canonical_path', 'canonical_sha256', 'canonical_bytes',
          'canonical_invocation_returned', 'canonical_workload_modified', 'identity_checks', 'host_expected'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def bad_constant(value):
    raise RuntimeError('Non-JSON constant: ' + value)


def markers(nonce, variant, target):
    require(re.fullmatch(r'[0-9a-f]{32}', nonce) and target in TARGETS and variant in RUNTIME_VARIANTS[target],
            'Unexpected workload oracle identity')
    api = TARGETS[target][0]
    negative = variant == 'baseline' and api < 34
    outcome = 'EXPECTED_CLASSVALUE_LINKAGE_ERROR' if negative else 'INITIALIZED'
    checks = 7 if negative else 14 if variant == 'candidate' else 13
    return ['API|' + str(api) + '|CLASSVALUE|' + str(api >= 34).lower(),
            *['CLASS|' + name + '|' + outcome for name in CLASSES],
            'WAEX_CLASS_METADATA_ART|' + nonce + '|' + variant + '|' + str(api) + '|' + str(checks) + '|PASS']


def validate_output(text, expected):
    require(isinstance(text, str) and len(text.encode('utf-8')) <= 65536,
            'Runtime transcript exceeds its bound')
    target, variant, nonce = expected['target'], expected['variant'], expected['nonce']
    require(target in TARGETS and variant in RUNTIME_VARIANTS[target] and
            re.fullmatch(r'[0-9a-f]{32}', nonce) and
            re.fullmatch(r'[0-9a-f]{32}', expected['phase_nonce']) and nonce != expected['phase_nonce'],
            'Expected invocation identity is invalid')
    lines = [line for line in text.splitlines() if line]
    require(len(lines) == 5 and lines[:4] == markers(nonce, variant, target) and
            lines[4].startswith(IDENTITY_PREFIX),
            'Expected exactly the unchanged four workload markers followed by one identity receipt')
    row = json.loads(lines[4][len(IDENTITY_PREFIX):], object_pairs_hook=unique_object,
                     parse_constant=bad_constant)
    require(type(row) is dict and set(row) == FIELDS, 'Unexpected identity receipt fields')
    api, _, page = TARGETS[target]
    directory = '/data/local/tmp/waex-art-recovery-' + expected['phase_nonce']
    expected_values = {
        'schema': 'WAEX_ART_PROFILE_IDENTITY_V1', 'status': 'PASS', 'target': target,
        'variant': variant, 'nonce': nonce, 'phase_nonce': expected['phase_nonce'],
        'sdk_int': api, 'expected_minor': minor(target), 'elf_class': 64, 'elf_machine': 62,
        'elf_endian': 'little', 'is_64_bit': True, 'uid': 2000,
        'application_page_size_bytes': page, 'page_size_method': 'android.system.Os.sysconf(_SC_PAGESIZE)',
        'boot_id_before': expected['boot_id'], 'boot_id_after': expected['boot_id'],
        'fingerprint': expected['fingerprint'], 'driver_path': directory + '/driver.jar',
        'canonical_path': directory + '/' + variant + '.jar',
        'driver_sha256': expected['driver']['jar_sha256'], 'driver_bytes': expected['driver']['jar_bytes'],
        'canonical_sha256': CANONICAL['variants'][variant]['jar_sha256'],
        'canonical_bytes': CANONICAL['variants'][variant]['jar_bytes'],
        'identity_checks': 13, 'canonical_invocation_returned': True, 'canonical_workload_modified': False,
        'sdk_int_full_field_read': api >= 36, 'sdk_full_helpers_called': api >= 36,
        'legacy_minor_zero_from_profile_only': api < 36,
    }
    for key, value in expected_values.items():
        require(type(row[key]) is type(value) and row[key] == value, 'Identity field differs: ' + key)
    require(type(row['pid']) is int and row['pid'] > 0 and row['hardware'] in ('ranchu', 'goldfish'),
            'Invalid own process PID or emulator hardware')
    require(re.fullmatch(r'/(?:system/bin|apex/com\.android\.(?:runtime|art)/bin)/app_process64', row['executable']),
            'Own executable is not the reviewed 64-bit app_process')
    require(isinstance(row['elf_header_hex'], str) and re.fullmatch(r'[0-9a-f]{128}', row['elf_header_hex']),
            'Own ELF header is incomplete')
    header = bytes.fromhex(row['elf_header_hex'])
    require(header[:7] == b'\x7fELF\x02\x01\x01' and
            struct.unpack_from('<HHI', header, 16) in ((2, 62, 1), (3, 62, 1)) and
            struct.unpack_from('<H', header, 52)[0] == 64 and
            row['elf_header_sha256'] == hashlib.sha256(header).hexdigest(), 'Own ELF proof differs')
    if api >= 36:
        require(type(row['sdk_int_full']) is int and row['sdk_int_full'] > 0 and
                type(row['sdk_full_major']) is int and row['sdk_full_major'] == api and
                type(row['sdk_full_minor']) is int and row['sdk_full_minor'] == minor(target),
                'SDK_INT_FULL must be observed and decoded by both real framework helpers')
    else:
        require(row['sdk_int_full'] is None and row['sdk_full_major'] is None and
                row['sdk_full_minor'] is None, 'Legacy profile cannot claim an SDK_INT_FULL observation')
    host = {key: expected[key] for key in ('run_id', 'attempt', 'workflow_commit', 'producer_manifest_sha256')}
    host.update(canonical_manifest_sha256=CANONICAL['manifest_sha256'],
                boot_id=expected['boot_id'], fingerprint=expected['fingerprint'])
    require(type(row['host_expected']) is dict and row['host_expected'] == host and
            all(type(row['host_expected'][key]) is str for key in host), 'Producer/run/boot binding differs')
    return {'status': 'PASS', 'workload_checks': int(lines[3].split('|')[-2]), 'identity_checks': 13,
            'baseline_negative_expected': variant == 'baseline' and api < 34,
            'identity': row, 'canonical_markers': lines[:4]}
