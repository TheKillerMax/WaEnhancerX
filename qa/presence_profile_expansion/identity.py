"""Validate the newly measured application identity without running a renderer."""
import hashlib
import re
import struct

SCHEMA = 'WAEX_PRESENCE_PROCESS_IDENTITY_V1'
FULL_METHOD = 'Build.VERSION.SDK_INT_FULL+Build.getMajorSdkVersion/getMinorSdkVersion(reflection)'
BOOT_METHOD = 'expected_host_boot_id_echo; measured separately by the adb supervisor'
PACKAGE = 'org.waex.qa.presence.host'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def validate_contract(value):
    expected = {'target', 'api', 'minor', 'page_bytes', 'nonce', 'run_id', 'boot_id',
                'producer_commit', 'github_run_id', 'github_run_attempt',
                'apk_sha256', 'apk_bytes', 'installed_path'}
    require(isinstance(value, dict) and set(value) == expected, 'Identity contract fields differ')
    match = re.fullmatch(r'api([0-9]+)(?:\.([0-9]+))?(-16k)?', value['target'])
    require(match is not None and type(value['api']) is int and 27 <= value['api'] <= 37
            and type(value['minor']) is int and 0 <= value['minor'] < 100000
            and (int(match[1]), int(match[2] or 0)) == (value['api'], value['minor']),
            'Identity target/API/minor differs')
    require(type(value['page_bytes']) is int and value['page_bytes'] == (16384 if match[3] else 4096)
            and (value['api'] >= 36 or value['minor'] == 0), 'Identity page/minor policy differs')
    require(re.fullmatch(r'[a-f0-9]{32}', value['nonce']) is not None
            and value['run_id'] == 'presence-' + value['nonce']
            and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', value['boot_id']) is not None,
            'Fresh nonce/run/boot binding is malformed')
    require(re.fullmatch(r'[a-f0-9]{40}', value['producer_commit']) is not None
            and re.fullmatch(r'[1-9][0-9]*', value['github_run_id']) is not None
            and value['github_run_attempt'] == '1', 'Producer/run binding is malformed')
    require(re.fullmatch(r'[a-f0-9]{64}', value['apk_sha256']) is not None
            and type(value['apk_bytes']) is int and 0 < value['apk_bytes'] <= 2 * 1024**2
            and re.fullmatch(r'/data/app/[A-Za-z0-9_./~+=-]+/base\.apk', value['installed_path']) is not None
            and '..' not in value['installed_path'].split('/')
            and PACKAGE in value['installed_path'], 'Installed producer identity is malformed')
    return value


def verified_process_identity(report, contract):
    contract = validate_contract(contract)
    identity = report.get('process_identity')
    fields = {'schema', 'status', 'target', 'api', 'sdk_int_full', 'sdk_full_major', 'sdk_full_minor',
              'sdk_full_method', 'minor_policy', 'process_is_64_bit', 'elf_class', 'elf_machine',
              'elf_endian', 'elf_header_hex', 'elf_header_sha256', 'executable_path',
              'process_uid', 'process_pid', 'application_page_size_bytes', 'page_size_method',
              'nonce', 'run_id', 'host_boot_id_binding', 'boot_binding_method',
              'producer_commit', 'producer_run_id', 'producer_attempt',
              'github_run_id', 'github_run_attempt', 'apk_sha256', 'apk_bytes', 'apk_path'}
    require(isinstance(identity, dict) and set(identity) == fields, 'Measured identity field set differs')
    require(identity['schema'] == SCHEMA and identity['status'] == 'PASS',
            'Measured process identity did not pass')
    expected = {'target': contract['target'], 'api': contract['api'],
                'application_page_size_bytes': contract['page_bytes'],
                'nonce': contract['nonce'], 'run_id': contract['run_id'],
                'host_boot_id_binding': contract['boot_id'], 'boot_binding_method': BOOT_METHOD,
                'producer_commit': contract['producer_commit'],
                'producer_run_id': contract['github_run_id'], 'producer_attempt': '1',
                'github_run_id': contract['github_run_id'], 'github_run_attempt': '1',
                'apk_sha256': contract['apk_sha256'], 'apk_bytes': contract['apk_bytes'],
                'apk_path': contract['installed_path'],
                'page_size_method': 'android.system.Os.sysconf(_SC_PAGE_SIZE)',
                'process_is_64_bit': True, 'elf_class': 2, 'elf_machine': 62, 'elf_endian': 'little'}
    for key, value in expected.items():
        require(type(identity[key]) is type(value) and identity[key] == value,
                'Measured process binding differs: ' + key)
    for key in ('process_uid', 'process_pid'):
        require(type(identity[key]) is int and identity[key] > 0, 'Invalid measured process number: ' + key)
    require(identity['process_uid'] >= 10000, 'Expected an ordinary application UID')
    require(isinstance(identity['executable_path'], str)
            and re.fullmatch(r'/[A-Za-z0-9_./@+-]+/app_process64', identity['executable_path']) is not None
            and '..' not in identity['executable_path'].split('/'), 'Unexpected measured process executable')
    require(isinstance(identity['elf_header_hex'], str)
            and re.fullmatch(r'[a-f0-9]{128}', identity['elf_header_hex']) is not None,
            'ELF header is not the exact bounded 64-byte observation')
    header = bytes.fromhex(identity['elf_header_hex'])
    require(header[:7] == b'\x7fELF\x02\x01\x01'
            and struct.unpack_from('<HHI', header, 16) in ((2, 62, 1), (3, 62, 1))
            and struct.unpack_from('<H', header, 52)[0] == 64
            and hashlib.sha256(header).hexdigest() == identity['elf_header_sha256'],
            'Measured ELF64/x86_64 header/hash differs')
    if contract['api'] >= 36:
        full = identity['sdk_int_full']
        require(type(full) is int and 0 < full <= 2147483647
                and type(identity['sdk_full_major']) is int and type(identity['sdk_full_minor']) is int
                and (identity['sdk_full_major'], identity['sdk_full_minor']) == (contract['api'], contract['minor'])
                and identity['sdk_full_method'] == FULL_METHOD
                and identity['minor_policy'] == 'MEASURED_SDK_INT_FULL',
                'Actual SDK_INT_FULL and reflected official helpers did not match the image')
    else:
        require(identity['sdk_int_full'] is None and identity['sdk_full_major'] is None
                and identity['sdk_full_minor'] is None and identity['sdk_full_method'] == 'NOT_READ_API_LT_36'
                and identity['minor_policy'] == 'LEGACY_MINOR_ZERO_POLICY_NOT_OBSERVED',
                'Legacy policy must not claim an SDK_INT_FULL or minor observation')
    require(report.get('run_id') == contract['run_id'] and type(report.get('api')) is int
            and report['api'] == contract['api'], 'Top-level process binding differs')
    return identity

