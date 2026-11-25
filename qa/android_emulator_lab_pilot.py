#!/usr/bin/env python3
"""Boot two reviewed, empty x86_64 AVD targets on the public Linux/KVM lab only."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time
import xml.etree.ElementTree as ET

from android_emulator_lab_preflight import (
    context_check, fetch_metadata, inspect_kvm, license_files, parse_feed,
    save, sdk_snapshot, sha256_file, tool_identity,
)

GIB = 1024 ** 3
RESERVE_BYTES = 2 * GIB
LOG_LIMIT = 8 * 1024 ** 2
TARGETS = {
    'api24': (24, 'system-images;android-24;google_apis;x86_64', 4096),
    'api35-16k': (35, 'system-images;android-35;google_apis_ps16k;x86_64', 16384),
}


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


def properties(path):
    return {key.strip(): value.strip() for line in path.read_text(encoding='utf-8').splitlines()
            if '=' in line and not line.lstrip().startswith('#') for key, value in [line.split('=', 1)]}


def package_identity(path, expected):
    root = ET.parse(path / 'package.xml').getroot()
    package = root.find('./{*}localPackage')
    require(package is not None and package.get('path') == expected['path'], 'Installed package path differs from the lock')
    revision = [int(package.findtext('./{*}revision/{*}' + name, '0')) for name in ('major', 'minor', 'micro')]
    require(revision == expected['revision'], 'Installed image revision differs from the lock')
    return {'path': str(path), 'revision': revision, 'package_xml_sha256': sha256_file(path / 'package.xml'),
            'source_properties_sha256': sha256_file(path / 'source.properties'),
            'source_properties': properties(path / 'source.properties')}


def checked_lock(path, target):
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
    entry = lock['targets'][target]
    api, image_path, page_size = TARGETS[target]
    require(entry['image']['path'] == image_path and entry['image']['api'] == api,
            'Target path/API differs from the two reviewed pilot targets')
    require(entry['application_page_size_bytes'] == page_size, 'Unexpected application page size target')
    require(entry['minimum_free_bytes'] >= 12 * GIB, 'Initial disk allowance must be at least 12 GiB')
    return lock, entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=sorted(TARGETS), required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    work = args.out.resolve()
    work.mkdir(parents=True, exist_ok=False)
    out = work / 'reports'
    out.mkdir()
    result = {'schema_version': 1, 'phase': 'boot_pilot_only', 'target': args.target, 'status': 'BLOCKED',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'issues': [],
              'apk_installed': False, 'licenses_accepted_by_this_run': False, 'emulator_process_started': False,
              'source_sha256': sha256_file(__file__), 'lock_sha256': sha256_file(args.lock)}
    emulator_process, emulator_stream, sdk, accepted_before = None, None, None, None
    before_tools = {}
    env = os.environ.copy()
    try:
        context_check(env)
        lock, entry = checked_lock(args.lock, args.target)
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
        for name, path in tools.items():
            before_tools[name] = tool_identity(path)
            require(before_tools[name].get('sha256') == lock['tool_sha256'].get(name), 'Tool changed since reviewed preflight: ' + name)
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
        _, devices = invoke(out, 'adb-devices-before', [str(tools['adb']), 'devices'], env)
        require(not re.search(r'^\S+\s+(device|offline|unauthorized)\s*$', devices, re.M), 'An existing ADB device makes this runner unsuitable')
        for port in (5580, 5581):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        avd_name = 'waex_pilot_' + args.target.replace('-', '_')
        avd_path = work / 'avd' / (avd_name + '.avd')
        invoke(out, 'create-fresh-avd', [str(avdmanager), 'create', 'avd', '--name', avd_name,
               '--package', expected['path'], '--path', str(avd_path)], env, timeout=90, input_bytes=b'no\n')
        config = avd_path / 'config.ini'
        values = properties(config)
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
            require(time.monotonic() - started < 420, 'Android boot deadline exceeded')
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
        guest = {}
        for key, arguments in {
            'sdk': ['getprop', 'ro.build.version.sdk'], 'release': ['getprop', 'ro.build.version.release'],
            'abi': ['getprop', 'ro.product.cpu.abi'], 'fingerprint': ['getprop', 'ro.build.fingerprint'],
            'application_page_size_bytes': ['getconf', 'PAGE_SIZE'], 'package_manager': ['pm', 'path', 'android'],
        }.items():
            _, value = invoke(out, 'guest-' + key, [str(tools['adb']), '-s', 'emulator-5580', 'shell', *arguments], env)
            guest[key] = value.strip()
        save(out, 'guest-identity.json', guest)
        require(guest['sdk'] == str(TARGETS[args.target][0]), 'Booted Android API differs from target')
        require(guest['abi'] == 'x86_64', 'Booted ABI differs from target')
        require(guest['application_page_size_bytes'] == str(entry['application_page_size_bytes']), 'Unexpected application-facing page size')
        require(guest['package_manager'].startswith('package:'), 'Android package manager is not ready')
        require(emulator_process.poll() is None, 'Emulator exited during final guest checks')
        result.update(android_booted=True, boot_seconds=round(time.monotonic() - started, 3), guest=guest,
                      x86_64_16k_simulation=(args.target == 'api35-16k'), real_arm64_16k_validated=False)
    except (OSError, RuntimeError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError) as exc:
        result['issues'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        if emulator_process is not None:
            result['emulator_exit_before_cleanup'] = emulator_process.poll()
            stop_owned(emulator_process)
            result['owned_emulator_reaped'] = emulator_process.poll() is not None
        if emulator_stream is not None:
            emulator_stream.close()
        if sdk is not None and accepted_before is not None:
            result['license_files_unchanged'] = license_files(sdk) == accepted_before
            if not result['license_files_unchanged']:
                result['issues'].append('License files changed during pilot')
        result['free_bytes_after'] = shutil.disk_usage(work).free
        result['status'] = 'PASS' if result.get('android_booted') and not result['issues'] else 'BLOCKED'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['limits'] = 'Empty AVD boot and application-facing page-size identity only. No APK, WAEX, WhatsApp, LSPosed or real ARM64 16 KiB validation.'
        save(out, 'pilot-result.json', result)
        save(out, 'manifest.json', {path.name: {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
                                  for path in sorted(out.iterdir()) if path.is_file()})
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
