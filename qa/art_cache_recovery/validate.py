"""Pure strict validator for the new cache fixture; no canonical markers accepted."""
import hashlib
import json
import re
import struct

FIELDS = {'schema', 'status', 'target', 'nonce', 'sdk_int', 'is_64_bit', 'uid', 'pid',
          'hardware', 'fingerprint', 'executable', 'elf_header_hex', 'elf_header_sha256',
          'application_page_size_bytes', 'page_size_method', 'boot_id_before', 'boot_id_after',
          'jar_path', 'jar_bytes', 'jar_sha256', 'producer', 'canonical_workload_invoked'}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def unique_object(items):
    value = {}
    for key, item in items:
        require(key not in value, 'Duplicate JSON field')
        value[key] = item
    return value


def validate_output(raw, expected):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384, 'Probe output byte bound differs')
    text = raw.decode('utf-8', errors='strict').replace('\r\n', '\n')
    require('\r' not in text and text.count('\n') == 1 and text.endswith('\n')
            and text.startswith('WAEX_ART_CACHE_IDENTITY|'), 'Probe must emit one exact identity line')
    value = json.loads(text[len('WAEX_ART_CACHE_IDENTITY|'):-1], object_pairs_hook=unique_object)
    require(type(value) is dict and set(value) == FIELDS, 'Probe receipt field set differs')
    required = {
        'schema': 'WAEX_ART_CACHE_PROCESS_IDENTITY_V1', 'status': 'PASS',
        'target': expected['target'], 'nonce': expected['nonce'],
        'sdk_int': int(expected['target'][3:]), 'is_64_bit': True, 'uid': 2000,
        'hardware': 'ranchu', 'fingerprint': expected['fingerprint'],
        'executable': '/system/bin/app_process64', 'application_page_size_bytes': 4096,
        'page_size_method': 'android.system.Os.sysconf(_SC_PAGESIZE)',
        'boot_id_before': expected['boot_id'], 'boot_id_after': expected['boot_id'],
        'jar_path': expected['jar_path'], 'jar_bytes': expected['jar_bytes'],
        'jar_sha256': expected['jar_sha256'], 'canonical_workload_invoked': False,
        'producer': expected['producer']}
    require(expected['target'] in ('api27', 'api28'), 'Unknown cache profile')
    require(re.fullmatch(r'[0-9a-f]{32}', expected['nonce']) is not None, 'Invalid expected nonce')
    for key, item in required.items():
        require(type(value[key]) is type(item) and value[key] == item, 'Identity differs: ' + key)
    require(type(value['pid']) is int and value['pid'] > 0, 'Invalid process PID')
    require(type(value['producer']) is dict and set(value['producer']) == {'workflow_commit', 'run_id', 'attempt'}
            and all(type(value['producer'][k]) is str for k in value['producer']), 'Malformed producer')
    require(type(value['elf_header_hex']) is str and re.fullmatch(r'[0-9a-f]{128}', value['elf_header_hex']) is not None,
            'ELF header encoding differs')
    elf = bytes.fromhex(value['elf_header_hex'])
    require(elf[:7] == b'\x7fELF\x02\x01\x01' and struct.unpack_from('<H', elf, 16)[0] in (2, 3)
            and struct.unpack_from('<H', elf, 18)[0] == 62 and struct.unpack_from('<I', elf, 20)[0] == 1
            and struct.unpack_from('<H', elf, 52)[0] == 64, 'Measured ELF is not x86_64')
    require(value['elf_header_sha256'] == hashlib.sha256(elf).hexdigest(), 'ELF header SHA differs')
    return {'status': 'PASS', 'scope': 'NEW_CACHE_FIXTURE_IDENTITY_ONLY', 'identity': value,
            'canonical_workload_repeated': False}
