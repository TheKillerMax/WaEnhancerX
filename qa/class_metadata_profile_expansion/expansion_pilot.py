#!/usr/bin/env python3
"""Boot two reviewed, empty x86_64 AVD targets on the public Linux/KVM lab only."""
import argparse
import datetime
import hashlib
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from android_emulator_lab_preflight import (
    fetch_metadata, inspect_kvm, license_files, parse_feed,
    save, sdk_snapshot, sha256_file, tool_identity,
)
import android_emulator_lab_adb as reviewed_adb
from expansion_contract import context_check, TARGETS as EXPANSION_TARGETS

GIB = 1024 ** 3
RESERVE_BYTES = 2 * GIB
LOG_LIMIT = 8 * 1024 ** 2
TARGETS = {
    'api24': (24, 'system-images;android-24;google_apis;x86_64', 4096),
    'api35-16k': (35, 'system-images;android-35;google_apis_ps16k;x86_64', 16384),
}

DEFAULT_LIMITS = 'Empty AVD boot and application-facing page-size identity only. No APK, WAEX, WhatsApp, LSPosed or real ARM64 16 KiB validation.'


@dataclass(frozen=True)
class BootContext:
    target: str
    api: int
    minor: int
    application_page_size_bytes: int
    adb: Path
    serial: str
    env: dict
    work: Path
    out: Path
    guest: dict
    entry: dict
    result: dict


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=10)
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def guard_space(path):
    free = shutil.disk_usage(path).free
    require(free >= RESERVE_BYTES, 'Runner disk reserve fell below 2 GiB')
    return free


def invoke(out, name, command, env, timeout=30, input_bytes=None, required=True):
    started = time.monotonic()
    log = out / (name + '.log')
    process = None
    reason = None
    try:
        with log.open('wb') as stream:
            process = subprocess.Popen(command, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            if input_bytes is not None:
                process.stdin.write(input_bytes)
                process.stdin.close()
            while process.poll() is None:
                guard_space(out)
                require(time.monotonic() - started < timeout, name + ' exceeded its deadline')
                require(log.stat().st_size <= LOG_LIMIT, name + ' exceeded its log limit')
                time.sleep(0.5)
    except (OSError, RuntimeError) as exc:
        reason = str(exc)
        stop_owned(process)
    result = {'command': list(map(str, command)), 'returncode': process.returncode if process else None,
              'elapsed_seconds': round(time.monotonic() - started, 3), 'failure': reason,
              'stdin': 'no custom hardware profile' if input_bytes is not None else 'closed'}
    save(out, name + '.command.json', result)
    if log.exists() and log.stat().st_size > LOG_LIMIT:
        result['failure'] = reason = name + ' exceeded its log limit'
        save(out, name + '.command.json', result)
    with log.open('rb') as stream:
        text = stream.read(LOG_LIMIT).decode('utf-8', errors='replace')
    if required:
        require(reason is None and result['returncode'] == 0, name + ' failed: ' + str(reason or result['returncode']))
    return result, text


def reviewed_tools(work, out, tools, env, pins):
    observed = {name: tool_identity(path) for name, path in tools.items()}
    # Preserve rejected identities too; the old loop failed before saving them.
    save(out, 'tool-identities-observed.json', observed)
    for name in tools:
        if name != 'adb':
            require(observed[name].get('sha256') == pins.get(name),
                    'Tool changed since reviewed preflight: ' + name)
    owned = None
    if observed['adb'].get('sha256') != pins.get('adb'):
        require(pins.get('adb') == reviewed_adb.MEMBERS['adb'][1],
                'ADB recovery does not match the original reviewed pin')
        owned = work / 'reviewed-platform-tools'
        invoke(out, 'acquire-reviewed-adb', [sys.executable, str(Path(reviewed_adb.__file__).resolve()),
               '--out', str(owned), '--report', str(out / 'reviewed-adb-acquisition.json')], env, timeout=90)
        reviewed_adb.installed_identity(owned)
        tools['adb'] = owned / 'adb'
    selected = {name: tool_identity(path) for name, path in tools.items()}
    save(out, 'tool-identities-selected.json', selected)
    for name in tools:
        require(selected[name].get('sha256') == pins.get(name),
                'Tool changed since reviewed preflight: ' + name)
    env['PATH'] = str(tools['adb'].parent) + os.pathsep + env.get('PATH', '')
    save(out, 'adb-selection.json', {'origin': 'owned_official_archive' if owned else 'preinstalled_reviewed',
         'observed': observed['adb'], 'selected': selected['adb'], 'required_sha256': pins['adb'],
         'sdk_modified': False})
    return selected, observed['adb'], owned


def unchanged_adb(sdk, observed, owned):
    require(tool_identity(sdk / 'platform-tools/adb') == observed, 'Preinstalled SDK ADB changed during the lab')
    if owned is not None:
        reviewed_adb.installed_identity(owned)



READY_BOOT_SECONDS = 420
READY_HORIZON_MS = 15000
READY_COMMANDS = {
    'boot': ['getprop', 'sys.boot_completed'],
    'pid_before': ['pidof', 'system_server'],
    'package': ['pm', 'path', 'android'],
    'user': ['am', 'get-started-user-state', '0'],
    'pid_after': ['pidof', 'system_server'],
}


def ready_pid(observation):
    checks = observation.get('checks', {})
    if set(checks) != set(READY_COMMANDS):
        return None
    if any(type(row.get('returncode')) is not int or row['returncode'] != 0
           or row.get('failure') is not None or not isinstance(row.get('text'), str)
           or len(row['text']) > 1024 for row in checks.values()):
        return None
    pid = checks['pid_before']['text']
    if (not re.fullmatch(r'[1-9][0-9]*', pid) or checks['pid_after']['text'] != pid
            or checks['boot']['text'] != '1'
            or checks['package']['text'] != 'package:/system/framework/framework-res.apk'
            or checks['user']['text'] != 'RUNNING_UNLOCKED'):
        return None
    return pid


def validate_guest_readiness(value):
    require(value.get('schema_version') == 1 and value.get('status') == 'PASS'
            and value.get('horizon_ms') == READY_HORIZON_MS
            and value.get('future_stability_claimed') is False, 'Incomplete guest readiness receipt')
    observations = value.get('observations', [])
    require(isinstance(observations, list) and len(observations) >= 3, 'Readiness needs three observations')
    previous = -1
    for row in observations:
        elapsed = row.get('elapsed_ms')
        require(type(elapsed) is int and previous < elapsed < READY_BOOT_SECONDS * 1000,
                'Readiness observation time is outside the total boot budget')
        previous = elapsed
    pid = ready_pid(observations[-1])
    require(pid is not None, 'Last readiness sample is incomplete')
    matching = []
    for row in reversed(observations):
        if ready_pid(row) != pid:
            break
        matching.append(row)
    require(len(matching) >= 3 and matching[0]['elapsed_ms'] - matching[-1]['elapsed_ms'] >= READY_HORIZON_MS,
            'Package/user/PID observations did not span the bounded readiness horizon')
    require(value.get('system_server_pid') == pid, 'Readiness PID differs')
    return value


def wait_for_guest_ready(out, adb, env, process, work, emulator_log, started):
    report = {'schema_version': 1, 'status': 'BLOCKED', 'horizon_ms': READY_HORIZON_MS,
              'future_stability_claimed': False, 'observations': []}
    try:
        while True:
            require(process.poll() is None, 'Emulator exited while observing guest readiness')
            require(time.monotonic() - started < READY_BOOT_SECONDS, 'Android readiness deadline exceeded')
            require(emulator_log.stat().st_size <= LOG_LIMIT, 'Emulator log exceeded 8 MiB')
            guard_space(work)
            checks = {}
            index = len(report['observations'])
            for key, arguments in READY_COMMANDS.items():
                remaining = READY_BOOT_SECONDS - (time.monotonic() - started)
                require(remaining > 0, 'Android readiness deadline exceeded')
                command, text = invoke(out, 'guest-ready-' + str(index) + '-' + key,
                                       [str(adb), '-s', 'emulator-5580', 'shell', *arguments], env,
                                       timeout=min(10, remaining), required=False)
                checks[key] = {'returncode': command['returncode'], 'failure': command['failure'],
                               'text': text.strip() if len(text) <= 1024 else '<output exceeds 1024 bytes>'}
            row = {'elapsed_ms': int(round((time.monotonic() - started) * 1000)), 'checks': checks}
            report['observations'].append(row)
            pid = ready_pid(row)
            matching = []
            for previous in reversed(report['observations']):
                if pid is None or ready_pid(previous) != pid:
                    break
                matching.append(previous)
            if (len(matching) >= 3
                    and matching[0]['elapsed_ms'] - matching[-1]['elapsed_ms'] >= READY_HORIZON_MS):
                report.update(status='PASS', system_server_pid=pid)
                return validate_guest_readiness(report)
            save(out, 'guest-readiness.json', report)
            remaining = READY_BOOT_SECONDS - (time.monotonic() - started)
            require(remaining > 0, 'Android readiness deadline exceeded')
            time.sleep(min(5, remaining))
    except Exception as error:
        report.update(status='BLOCKED', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        save(out, 'guest-readiness.json', report)


def capture_guest_diagnostics(out, adb, env, process):
    report = {'status': 'PARTIAL', 'acquisition_budget_seconds': 45,
              'command_shutdown_grace_seconds': 20, 'poll_interval_seconds': 0.5,
              'commands': {}, 'errors': []}
    started = time.monotonic()
    commands = {
        'crash': ['logcat', '-b', 'crash', '-d', '-v', 'threadtime', '-t', '300'],
        'system': ['logcat', '-b', 'system', '-d', '-v', 'threadtime', '-t', '700'],
        'events': ['logcat', '-b', 'events', '-d', '-v', 'threadtime', '-t', '500'],
        'user': ['shell', 'am', 'get-started-user-state', '0'],
        'pid': ['shell', 'pidof', 'system_server'],
        'memory': ['shell', 'cat', '/proc/meminfo'],
        'data-space': ['shell', 'df', '-k', '/data'],
        'properties': ['shell', 'getprop'],
    }
    for name, command in commands.items():
        remaining = 45 - (time.monotonic() - started)
        if remaining <= 0 or process.poll() is not None:
            report['errors'].append('Diagnostic budget exhausted or owned emulator exited')
            break
        try:
            observed, _ = invoke(out, 'guest-diagnostic-' + name,
                                 [str(adb), '-s', 'emulator-5580', *command], env,
                                 timeout=min(6, remaining), required=False)
            report['commands'][name] = observed
            if observed['failure'] is not None or observed['returncode'] != 0:
                report['errors'].append(name + ': ' + str(observed['failure'] or observed['returncode']))
        except Exception as error:
            report['errors'].append(name + ': ' + type(error).__name__ + ': ' + str(error))
    if not report['errors'] and len(report['commands']) == len(commands):
        report['status'] = 'COLLECTED'
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    save(out, 'guest-diagnostics.json', report)
    return report


def properties(path):
    return {key.strip(): value.strip() for line in path.read_text(encoding='utf-8').splitlines()
            if '=' in line and not line.lstrip().startswith('#') for key, value in [line.split('=', 1)]}


def repair_decimal_avd_index(raw, expected, config, owned_avd_path):
    """Correct only the known avdmanager decimal-target serialization defect.

    This operates on a fresh, owned runner AVD, never on an attached device.
    The package, image directory, GPU and runtime readiness gates are unchanged.
    """
    parts = expected['path'].split(';')
    require(len(parts) == 4 and parts[0] == 'system-images'
            and parts[3] == 'x86_64', 'Unexpected system image path')
    target = parts[1]
    match = re.fullmatch(r'android-(\d+)\.(\d+)', target)
    require(match is not None, 'Only decimal SDK package targets are eligible')
    require((int(match[1]), int(match[2])) == (expected['api'], expected['minor']),
            'Decimal SDK metadata differs from package target')
    require(config.get('image.sysdir.1', '').rstrip('/') == '/'.join(parts),
            'AVD image directory differs from the pinned package')
    require(0 < len(raw) <= 16384 and b'\x00' not in raw, 'AVD index size/encoding invalid')
    text = raw.decode('utf-8', errors='strict')
    lines = text.splitlines(keepends=True)
    keys = {}
    for i, line in enumerate(lines):
        logical = line.rstrip('\r\n')
        if not logical.strip() or logical.lstrip().startswith('#'):
            continue
        key, sep, value = logical.partition('=')
        require(sep == '=' and key == key.strip() and key not in keys,
                'Malformed or duplicate AVD index field')
        keys[key] = (i, value)
    require('target' in keys and 'path' in keys, 'AVD index lacks target or path')
    require(keys['path'][1] == str(owned_avd_path), 'AVD index path is not the owned AVD')
    i, old = keys['target']
    require(old in (target, 'android-0'), 'Unexpected AVD index target: ' + old)
    if old == 'android-0':
        lines[i] = 'target=' + target + lines[i][len('target=android-0'):]
    after = ''.join(lines).encode('utf-8')
    return after, {
        'image': expected['path'], 'target_before': old, 'target_after': target,
        'owned_avd_path': str(owned_avd_path), 'corrected': old != target,
        'before_sha256': hashlib.sha256(raw).hexdigest(),
        'after_sha256': hashlib.sha256(after).hexdigest(),
    }


def legacy_auxv_page_size(elf, raw):
    # Read the exact /system/bin/cat executable's ELF header before parsing its AUXV.
    require(len(elf) == 64 and elf[:7] == b'\x7fELF\x02\x01\x01',
            'AUXV reader is not a complete ELF64 little-endian executable')
    require(struct.unpack_from('<HHI', elf, 16) in ((2, 62, 1), (3, 62, 1)) and
            struct.unpack_from('<H', elf, 52)[0] == 64, 'AUXV reader ELF machine/version/header is invalid')
    require(0 < len(raw) <= 8192 and len(raw) % 16 == 0, 'AUXV is empty, oversized or truncated')
    pairs = list(struct.iter_unpack('<QQ', raw))
    require(pairs[-1] == (0, 0), 'AUXV lacks its terminal AT_NULL')
    values = {}
    for tag, value in pairs[:-1]:
        require(tag != 0 and tag not in values, 'AUXV contains an early terminator or duplicate tag')
        values[tag] = value
    require(values.get(6) == 4096, 'Legacy AUXV AT_PAGESZ is missing or differs from 4096')
    return 4096


def application_page_size(out, adb, env, guest, expected_page_size):
    require(guest.get('sdk') in tuple(str(api) for api in range(24, 38)) and
            guest.get('abi') == 'x86_64' and type(expected_page_size) is int and
            expected_page_size in (4096, 16384), 'Unexpected page-size observation target')
    legacy = int(guest['sdk']) <= 28
    require(not legacy or expected_page_size == 4096,
            'Legacy AUXV observation is limited to reviewed 4 KiB targets')
    policy = {'api': int(guest['sdk']), 'expected_application_page_size_bytes': expected_page_size,
              'getconf_requested': not legacy,
              'policy': 'API24-28 use ELF64/AUXV directly; API29+ require successful getconf'}
    save(out, 'guest-page-size-policy.json', policy)
    if not legacy:
        command, value = invoke(out, 'guest-application_page_size_bytes',
                                [str(adb), '-s', 'emulator-5580', 'shell', 'getconf', 'PAGE_SIZE'],
                                env, required=False)
        require(command['failure'] is None and command['returncode'] == 0,
                'Page-size getconf command failed on a modern target')
        require(re.fullmatch(r'[1-9][0-9]*', value.strip()), 'getconf returned an invalid page size')
        require(value.strip() == str(expected_page_size), 'getconf page size differs from the reviewed target')
        return value.strip(), {'method': 'getconf_PAGE_SIZE', 'getconf_requested': True}
    # Old guest shells report the same absent getconf as either 127 or 255.
    # Select the existing binary proof from the reviewed API, never from a failed command.
    # exec-out transports binary bytes without a PTY/ONLCR conversion. No root or APK.
    elf_path, auxv_path = out / 'guest-auxv-reader-elf.log', out / 'guest-legacy-auxv.log'
    reader_identity = {}
    try:
        invoke(out, 'guest-auxv-reader-elf',
               [str(adb), '-s', 'emulator-5580', 'exec-out', '/system/bin/cat', '/system/bin/cat'], env)
    finally:
        if elf_path.exists():
            reader_identity = {'full_executable_bytes': elf_path.stat().st_size,
                               'full_executable_sha256': sha256_file(elf_path),
                               'retained_bytes': min(64, elf_path.stat().st_size),
                               'capture': 'exec-out /system/bin/cat /system/bin/cat; only the ELF header is retained'}
            with elf_path.open('rb') as stream:
                header = stream.read(64)
            elf_path.write_bytes(header)
            save(out, 'guest-auxv-reader-identity.json', reader_identity)
    invoke(out, 'guest-legacy-auxv',
           [str(adb), '-s', 'emulator-5580', 'exec-out', '/system/bin/cat', '/proc/self/auxv'], env)
    size = legacy_auxv_page_size(elf_path.read_bytes(), auxv_path.read_bytes())
    return str(size), {'method': 'legacy_Bionic_sysconf_AT_PAGESZ', 'getconf_requested': False,
                       'api': int(guest['sdk']), 'reader': '/system/bin/cat',
                       'reader_identity': reader_identity,
                       'reader_elf_class': 64, 'reader_endian': 'little', 'pointer_bytes': 8,
                       'reader_elf_header_sha256': sha256_file(elf_path),
                       'auxv_bytes': auxv_path.stat().st_size, 'auxv_sha256': sha256_file(auxv_path),
                       'scope': 'Direct observation on API24-28 x86_64/4 KiB only; no fallback after a failed command'}


def read_full_sdk_property(out, adb, env, api):
    require(type(api) is int and 24 <= api <= 37, 'Unexpected API for the SDK property policy')
    # SDK_INT_FULL and its source property were introduced with API36. Older
    # getprop implementations need not successfully query an unknown property.
    # Do not turn their optional metadata lookup into a boot prerequisite.
    observation = {'api': api, 'requested': api >= 36,
                   'property': 'ro.build.version.sdk_full',
                   'policy': 'Require major/minor property only on API36 and later'}
    save(out, 'guest-sdk-full-policy.json', observation)
    if api < 36:
        return ''
    _, value = invoke(out, 'guest-sdk_full_property',
                      [str(adb), '-s', 'emulator-5580', 'shell', 'getprop', observation['property']], env)
    return value.strip()


def guest_version_identity(guest, expected):
    require(guest['sdk'] == str(expected['api']), 'Booted Android API differs from image metadata')
    raw = guest.get('sdk_full_property', '')
    observation = {'api': expected['api'], 'metadata_minor': expected['minor'],
                   'sdk_full_property': raw, 'sdk_int_full_from_property': None,
                   'java_sdk_int_full_field_read': False, 'minor_verified': False}
    if expected['api'] >= 36:
        match = re.fullmatch(r'([0-9]+)(?:\.([0-9]+))?', raw)
        require(match is not None, 'Missing or malformed ro.build.version.sdk_full')
        major, minor = int(match[1]), int(match[2] or 0)
        require(major < 21474 and minor < 100000, 'SDK full version exceeds the AOSP bounds')
        require((major, minor) == (expected['api'], expected['minor']),
                'Booted SDK major/minor differs from image metadata')
        observation.update(sdk_int_full_from_property=major * 100000 + minor, minor_verified=True)
    else:
        require(expected['minor'] == 0, 'Legacy API metadata has an unsupported minor version')
    return observation


def package_identity(path, expected):
    root = ET.parse(path / 'package.xml').getroot()
    package = root.find('./{*}localPackage')
    require(package is not None and package.get('path') == expected['path'], 'Installed package path differs from the lock')
    revision = [int(package.findtext('./{*}revision/{*}' + name, '0')) for name in ('major', 'minor', 'micro')]
    require(revision == expected['revision'], 'Installed image revision differs from the lock')
    return {'path': str(path), 'revision': revision, 'package_xml_sha256': sha256_file(path / 'package.xml'),
            'source_properties_sha256': sha256_file(path / 'source.properties'),
            'source_properties': properties(path / 'source.properties')}


def reviewed_preflight_lock(path):
    lock = json.loads(path.read_text(encoding='utf-8'))
    require(lock.get('schema_version') == 1 and lock.get('ready') is True,
            'Pilot remains disabled until a real successful preflight has been reviewed')
    evidence = lock.get('preflight', {})
    require(evidence.get('status') == 'PASS', 'The reviewed preflight did not pass')
    require(evidence.get('bootstrap_status') == 'PASS' and
            re.fullmatch(r'[0-9a-f]{64}', evidence.get('bootstrap_result_sha256', '')),
            'A reviewed successful bootstrap receipt is required')
    require(re.fullmatch(r'https://github\.com/TheKillerMax/WaEnhancerX/actions/runs/\d+', evidence.get('run_url', '')),
            'A concrete public preflight run is required')
    require(re.fullmatch(r'[0-9a-f]{40}', evidence.get('head_sha', '')), 'Preflight commit SHA is missing')
    for name in ('preflight-result.json', 'catalog.json', 'tool-identities.json', 'installed-component-properties.json'):
        require(re.fullmatch(r'[0-9a-f]{64}', evidence.get('report_sha256', {}).get(name, '')),
                'Preflight report identity is missing: ' + name)
    for name in ('qa/android_emulator_lab_preflight.py', 'qa/android_emulator_lab_bootstrap.py'):
        expected_sha = lock.get('source_sha256', {}).get(name, '')
        source = Path(__file__).resolve().parent.parent / name
        require(re.fullmatch(r'[0-9a-f]{64}', expected_sha) and source.is_file() and sha256_file(source) == expected_sha,
                'Checkout source changed since the reviewed preflight: ' + name)
    return lock


def checked_lock(path, target):
    lock = reviewed_preflight_lock(path)
    entry = lock['targets'][target]
    api, image_path, page_size = TARGETS[target]
    require(entry['image']['path'] == image_path and entry['image']['api'] == api,
            'Target path/API differs from the two reviewed pilot targets')
    require(entry['application_page_size_bytes'] == page_size, 'Unexpected application page size target')
    require(entry['minimum_free_bytes'] >= 12 * GIB, 'Initial disk allowance must be at least 12 GiB')
    return lock, entry


def main(argv=None, *, targets=None, read_lock=checked_lock, boot_action=None, phase='boot_pilot_only',
         result_name='pilot-result.json', limits=DEFAULT_LIMITS):
    require(targets is not None and targets == EXPANSION_TARGETS,
            "Only the seventeen pending ART profiles may use this derived controller")
    require(re.fullmatch(r'[a-z0-9_-]+\.json', result_name), 'Invalid result filename')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=sorted(targets), required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    work = args.out.resolve()
    work.mkdir(parents=True, exist_ok=False)
    out = work / 'reports'
    out.mkdir()
    result = {'schema_version': 1, 'phase': phase, 'target': args.target, 'status': 'BLOCKED',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'issues': [],
              'apk_install_attempted': False, 'apk_installed': False, 'licenses_accepted_by_this_run': False, 'emulator_process_started': False,
              'source_sha256': sha256_file(__file__), 'lock_sha256': sha256_file(args.lock),
              'github_run_id': os.environ.get('GITHUB_RUN_ID'),
              'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'github_head_sha': os.environ.get('GITHUB_SHA'), 'requested_phase_completed': False}
    emulator_process, emulator_stream, sdk, accepted_before = None, None, None, None
    before_tools, tools = {}, {}
    observed_adb, owned_adb = None, None
    env = os.environ.copy()
    try:
        context_check(env)
        lock, entry = read_lock(args.lock, args.target)
        save(out, 'reviewed-preflight.json', lock['preflight'])
        expected = entry['image']
        result['host_kvm'] = inspect_kvm()
        require(result['host_kvm']['usable'], 'KVM unavailable; no software-CPU fallback is allowed')
        result['free_bytes_before'] = guard_space(work)
        require(result['free_bytes_before'] >= entry['minimum_free_bytes'], 'Insufficient free disk for the reviewed image allowance')
        sdk = Path(env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or '/missing/sdk').resolve()
        require(sdk.is_dir(), 'Preinstalled SDK is required')
        env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), ANDROID_USER_HOME=str(work / 'android-user'),
                   ANDROID_AVD_HOME=str(work / 'avd'), ANDROID_EMULATOR_HOME=str(work / 'emulator-state'))
        for variable in ('ANDROID_USER_HOME', 'ANDROID_AVD_HOME', 'ANDROID_EMULATOR_HOME'):
            Path(env[variable]).mkdir()
        tools = {'sdkmanager': sdk / 'cmdline-tools/latest/bin/sdkmanager',
                 'emulator': sdk / 'emulator/emulator', 'adb': sdk / 'platform-tools/adb',
                 'java': Path(shutil.which('java') or '/missing/java')}
        before_tools, observed_adb, owned_adb = reviewed_tools(work, out, tools, env, lock['tool_sha256'])
        avdmanager = sdk / 'cmdline-tools/latest/bin/avdmanager'
        require(avdmanager.is_file(), 'Preinstalled avdmanager is required')
        save(out, 'tool-identities-before.json', {**before_tools, 'avdmanager': tool_identity(avdmanager)})
        emulator_revision_text = properties(sdk / 'emulator/source.properties').get('Pkg.Revision', '')
        emulator_revision = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', emulator_revision_text)
        require(emulator_revision, 'Unknown preinstalled emulator revision: ' + emulator_revision_text)
        for dependency in expected['dependencies']:
            require(dependency['path'] == 'emulator', 'Unexpected image dependency would require another installation')
            require(tuple(map(int, emulator_revision.groups())) >= tuple(dependency['min_revision']), 'Preinstalled emulator is too old')
        accepted_before = license_files(sdk)
        save(out, 'licenses-before.json', accepted_before)
        root, metadata_identity = fetch_metadata(expected['source_metadata'])
        packages = parse_feed(root, expected['source_metadata'], accepted_before)
        current = next((p for p in packages if p['path'] == expected['path']), None)
        require(current is not None and current['license_already_accepted'], 'Current image license is not already accepted')
        identity_fields = ('path', 'api', 'minor', 'tag', 'abi', 'revision', 'license_id', 'license_text_sha1', 'archives', 'dependencies')
        require(all(current[key] == expected[key] for key in identity_fields), 'Official package metadata changed since review')
        save(out, 'current-image-metadata.json', {'repository': metadata_identity, 'image': current})
        invoke(out, 'accel-check', [str(tools['emulator']), '-accel-check'], env)
        _, gpu_help = invoke(out, 'gpu-help', [str(tools['emulator']), '-help-gpu'], env)
        require(re.search(r'\bswiftshader\b', gpu_help), 'Reviewed SwiftShader GPU mode is not advertised by this emulator')
        before = sdk_snapshot(sdk)
        save(out, 'sdk-before-install.json', before)
        invoke(out, 'install-one-image', [str(tools['sdkmanager']), '--sdk_root=' + str(sdk), '--channel=0',
               '--install', expected['path']], env, timeout=600)
        image_path = sdk.joinpath(*expected['path'].split(';'))
        save(out, 'installed-image.json', package_identity(image_path, expected))
        after = sdk_snapshot(sdk)
        save(out, 'sdk-after-install.json', after)
        allowed_prefix = expected['path'].replace(';', '/') + '/'
        unexpected = [key for key in set(before) | set(after) if before.get(key) != after.get(key) and not key.startswith(allowed_prefix)]
        require(not unexpected, 'Installer changed metadata outside the selected image: ' + ', '.join(unexpected))
        require(license_files(sdk) == accepted_before, 'License acceptance files changed during installation')
        for name, path in tools.items():
            require(tool_identity(path) == before_tools[name], 'Installer changed a preinstalled tool: ' + name)
        unchanged_adb(sdk, observed_adb, owned_adb)
        _, devices = invoke(out, 'adb-devices-before', [str(tools['adb']), 'devices'], env)
        require(not re.search(r'^\S+\s+(device|offline|unauthorized)\s*$', devices, re.M), 'An existing ADB device makes this runner unsuitable')
        for port in (5580, 5581):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        avd_name = 'waex_pilot_' + args.target.replace('-', '_').replace('.', '_')
        avd_path = work / 'avd' / (avd_name + '.avd')
        invoke(out, 'create-fresh-avd', [str(avdmanager), 'create', 'avd', '--name', avd_name,
               '--package', expected['path'], '--path', str(avd_path)], env, timeout=90, input_bytes=b'no\n')
        config = avd_path / 'config.ini'
        values = properties(config)
        # Old avdmanager versions can serialize decimal SDK targets as android-0.
        # Preserve the actual pre-launch index and only repair that exact mismatch.
        if re.fullmatch(r'android-\d+\.\d+', expected['path'].split(';')[1]):
            index = Path(env['ANDROID_AVD_HOME']) / (avd_name + '.ini')
            require(index.is_file() and not index.is_symlink() and
                    index.resolve().parent == (work / 'avd').resolve(),
                    'Fresh owned AVD index is missing or not a regular owned file')
            require(config.is_file() and not config.is_symlink() and
                    avd_path.resolve().parent == (work / 'avd').resolve(),
                    'Fresh AVD config is not owned')
            require(0 < index.stat().st_size <= 16384, 'Fresh AVD index exceeds reviewed bounds')
            raw = index.read_bytes()
            (out / 'fresh-avd-index-before.ini').write_bytes(raw)
            save(out, 'fresh-avd-config-before.json', values)
            after, metadata = repair_decimal_avd_index(raw, expected, values, avd_path)
            if metadata['corrected']:
                index.write_bytes(after)
            require(index.read_bytes() == after, 'AVD index write/readback differs')
            (out / 'fresh-avd-index-after.ini').write_bytes(after)
            save(out, 'avd-target-metadata.json', metadata)
            result['avd_target_metadata'] = metadata
        values.update({'disk.dataPartition.size': '2G', 'hw.ramSize': '2048', 'hw.cpu.ncore': '2',
                       'hw.lcd.width': '480', 'hw.lcd.height': '800', 'hw.lcd.density': '160'})
        config.write_text(''.join(key + '=' + value + '\n' for key, value in values.items()), encoding='utf-8')
        save(out, 'fresh-avd-config.json', values)
        command = [str(tools['emulator']), '-avd', avd_name, '-port', '5580', '-accel', 'on',
                   '-gpu', 'swiftshader', '-memory', '2048', '-cores', '2', '-skin', '480x800',
                   '-no-window', '-no-audio', '-no-boot-anim', '-no-snapshot']
        save(out, 'emulator-command.json', {'command': command, 'tcg_allowed': False, 'adb_serial': 'emulator-5580'})
        emulator_log = out / 'emulator.log'
        emulator_stream = emulator_log.open('wb')
        emulator_process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=emulator_stream,
                                            stderr=subprocess.STDOUT, env=env, start_new_session=True)
        result['emulator_process_started'] = True
        result['emulator_pid'] = emulator_process.pid
        started = time.monotonic()
        timeline = []
        while True:
            require(emulator_process.poll() is None, 'Emulator exited before boot: ' + str(emulator_process.returncode))
            require(time.monotonic() - started < READY_BOOT_SECONDS, 'Android boot deadline exceeded')
            require(emulator_log.stat().st_size <= LOG_LIMIT, 'Emulator log exceeded 8 MiB')
            free = guard_space(work)
            command_result, output = invoke(out, 'adb-boot-latest', [str(tools['adb']), '-s', 'emulator-5580',
                                           'shell', 'getprop', 'sys.boot_completed'], env, timeout=10, required=False)
            complete = command_result['returncode'] == 0 and command_result['failure'] is None and output.strip() == '1'
            timeline.append({'elapsed_seconds': round(time.monotonic() - started, 3), 'free_bytes': free,
                             'adb_returncode': command_result['returncode'], 'boot_complete': complete})
            save(out, 'boot-timeline.json', timeline)
            if complete:
                break
            time.sleep(5)
        if expected['api'] >= 36:
            result['guest_readiness'] = wait_for_guest_ready(out, tools['adb'], env, emulator_process,
                                                            work, emulator_log, started)
        guest = {}
        for key, arguments in {
            'sdk': ['getprop', 'ro.build.version.sdk'], 'release': ['getprop', 'ro.build.version.release'],
            'abi': ['getprop', 'ro.product.cpu.abi'], 'fingerprint': ['getprop', 'ro.build.fingerprint'],
            'package_manager': ['pm', 'path', 'android'],
        }.items():
            _, value = invoke(out, 'guest-' + key, [str(tools['adb']), '-s', 'emulator-5580', 'shell', *arguments], env)
            guest[key] = value.strip()
        require(guest['sdk'] == str(expected['api']), 'Booted API differs before querying version extensions')
        guest['sdk_full_property'] = read_full_sdk_property(out, tools['adb'], env, expected['api'])
        guest['application_page_size_bytes'], page_observation = application_page_size(
            out, tools['adb'], env, guest, entry['application_page_size_bytes'])
        save(out, 'application-page-size-observation.json', page_observation)
        save(out, 'guest-identity.json', guest)
        require(expected['api'] == targets[args.target][0], 'Image metadata API differs from target')
        version_observation = guest_version_identity(guest, expected)
        save(out, 'guest-version-identity.json', version_observation)
        require(guest['abi'] == 'x86_64', 'Booted ABI differs from target')
        require(guest['application_page_size_bytes'] == str(entry['application_page_size_bytes']), 'Unexpected application-facing page size')
        require(guest['package_manager'].startswith('package:'), 'Android package manager is not ready')
        require(emulator_process.poll() is None, 'Emulator exited during final guest checks')
        result.update(android_booted=True, boot_seconds=round(time.monotonic() - started, 3), guest=guest,
                      guest_version=version_observation,
                      x86_64_16k_simulation=(entry['application_page_size_bytes'] == 16384), real_arm64_16k_validated=False)
        if boot_action is not None:
            context = BootContext(args.target, expected['api'], expected['minor'],
                                  entry['application_page_size_bytes'], tools['adb'], 'emulator-5580',
                                  env, work, out, guest, entry, result)
            receipt = boot_action(context)
            require(isinstance(receipt, dict) and receipt.get('status') == 'PASS',
                    'Requested post-boot phase did not return a complete PASS receipt')
            result['phase_receipt'] = receipt
        result['requested_phase_completed'] = True
    except (OSError, RuntimeError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError) as exc:
        result['issues'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        if emulator_process is not None:
            result['emulator_exit_before_cleanup'] = emulator_process.poll()
            if targets[args.target][0] >= 36:
                try:
                    result['guest_diagnostics'] = capture_guest_diagnostics(out, tools['adb'], env, emulator_process)
                except Exception as error:
                    result['guest_diagnostic_error'] = type(error).__name__ + ': ' + str(error)
            stop_owned(emulator_process)
            result['owned_emulator_reaped'] = emulator_process.poll() is not None
        if emulator_stream is not None:
            emulator_stream.close()
        if before_tools:
            try:
                after_tools = {name: tool_identity(path) for name, path in tools.items()}
                save(out, 'tool-identities-after.json', after_tools)
                require(after_tools == before_tools, 'Selected tools changed during the lab')
                unchanged_adb(sdk, observed_adb, owned_adb)
                result['selected_tools_unchanged'] = True
            except (OSError, RuntimeError) as exc:
                result['selected_tools_unchanged'] = False
                result['issues'].append(type(exc).__name__ + ': ' + str(exc))
        if sdk is not None and accepted_before is not None:
            result['license_files_unchanged'] = license_files(sdk) == accepted_before
            if not result['license_files_unchanged']:
                result['issues'].append('License files changed during pilot')
        result['free_bytes_after'] = shutil.disk_usage(work).free
        result['status'] = 'PASS' if result.get('android_booted') and result['requested_phase_completed'] and not result['issues'] else 'BLOCKED'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['limits'] = limits
        save(out, result_name, result)
        save(out, 'manifest.json', {path.relative_to(out).as_posix(): {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
                                  for path in sorted(out.rglob('*')) if path.is_file() and path != out / 'manifest.json'})
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit('Use the reviewed ART expansion runner; standalone pilot execution is disabled')
