#!/usr/bin/env python3
"""Install, observe and remove only the neutral package in a controller-owned fresh AVD."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

import validate_native_constants_probe as validate

require = validate.require


def run_probe(adb, serial, api, page_size, apk, apk_sha256, build_receipt, out, env=None):
    require(serial == validate.SERIAL, 'Only the assigned fresh AVD serial is allowed')
    require(type(api) is int and 24 <= api <= 37 and type(page_size) is int
            and page_size in (4096, 16384), 'Invalid guest expectations')
    require(Path(adb).name in ('adb', 'adb.exe'), 'Expected explicit ADB executable')
    apk, out = Path(apk).resolve(), Path(out).resolve()
    require(not out.exists(), 'Evidence directory must be new')
    result = {'schema': 'WAEXDIAG_PROBE_HOST_V2', 'status': 'FAIL',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': validate.SCOPE, 'serial': serial, 'expected_api': api,
              'expected_application_page_size_bytes': page_size, 'commands': [],
              'initial_package_absent': False, 'installation_attempted': False,
              'cleanup_verified': False, 'other_libraries_or_commands_tested': False}
    out.mkdir(parents=True)
    env = dict(os.environ if env is None else env)
    pulled = []
    def call(name, args, timeout=30):
        command = [str(adb), '-s', serial, *map(str, args)]
        item = {'name': name, 'command': command}
        result['commands'].append(item)
        began = time.monotonic()
        try:
            run = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env, timeout=timeout)
            item['exit_code'] = run.returncode
            require(len(run.stdout) <= 1024**2, 'ADB output exceeded limit: ' + name)
            text = run.stdout.decode('utf-8', errors='replace')
            (out / (str(len(result['commands'])).zfill(2) + '-' + name + '.log')).write_bytes(run.stdout)
            require(run.returncode == 0, 'ADB command failed: ' + name)
            return text.strip()
        except subprocess.TimeoutExpired:
            item['timed_out'] = True
            raise
        finally:
            item['elapsed_seconds'] = round(time.monotonic() - began, 3)

    def present(label):
        text = call(label, ['shell', 'pm', 'list', 'packages', '--user', '0', validate.PACKAGE])
        require(text in ('', 'package:' + validate.PACKAGE), 'Ambiguous package listing')
        return text != ''

    def installed_hash(label):
        text = call(label + '-path', ['shell', 'pm', 'path', '--user', '0', validate.PACKAGE])
        lines = text.splitlines()
        require(len(lines) == 1 and lines[0].startswith('package:'), 'Expected one installed APK')
        remote = lines[0][len('package:'):]
        require(re.fullmatch(r'/data/app/[A-Za-z0-9._/+=~-]+\.apk', remote)
                and '..' not in remote.split('/') and remote.endswith('/base.apk'), 'Unsafe APK path')
        local = out / (label + '.apk')
        require(not local.exists(), 'Readback destination already exists')
        pulled.append(local)
        call(label + '-pull', ['pull', remote, local], 45)
        require(local.is_file() and local.stat().st_size == apk.stat().st_size, 'Installed APK size differs')
        actual = validate.digest(local.read_bytes())
        require(actual == apk_sha256, 'Installed APK hash differs; ownership is unverified')
        local.unlink()
        return {'path': remote, 'sha256': actual}

    try:
        build = validate.strict_json(Path(build_receipt).read_text(encoding='utf-8'))
        require(build['status'] == 'PASS_BUILD_ONLY' and build['schema'] == 'WAEXDIAG_PROBE_BUILD_V2'
                and build['scope'] == validate.SCOPE and build['package'] == validate.PACKAGE
                and build['ephemeral_key_absent'] is True and build['license_registry_unchanged'] is True,
                'Build receipt is not accepted')
        require(build['input_files'] == validate.source_inventory(), 'Build and runtime harness sources differ')
        require(build['apk']['apk_sha256'] == apk_sha256, 'Build/expected APK hash mismatch')
        for key, expected in (('source_revision', validate.SOURCE_REVISION), ('source_sha256', validate.SOURCE_SHA256),
                              ('cmake_sha256', validate.CMAKE_SHA256), ('contract_sha256', validate.CONTRACT_SHA256)):
            require(build[key] == expected, 'Build identity: ' + key)
        elf_sha = build['native']['elf_sha256']
        result['apk'] = validate.inspect_apk(apk, apk_sha256, elf_sha)
        require(result['apk'] == build['apk'], 'Build and observed APK inventory differ')
        require(call('state', ['get-state']) == 'device', 'AVD is unavailable')
        properties = {'ro.kernel.qemu': '1', 'sys.boot_completed': '1',
                      'ro.build.version.sdk': str(api), 'ro.product.cpu.abi': 'x86_64'}
        for prop, expected in properties.items():
            require(call('prop-' + prop, ['shell', 'getprop', prop]) == expected, 'Guest identity: ' + prop)
        require(not present('initial-packages'), 'The probe package already exists')
        result['initial_package_absent'] = True
        result['installation_attempted'] = True
        install = call('install', ['install', '-t', apk], 90)
        require(install.splitlines().count('Success') == 1 and 'Failure' not in install
                and 'INSTALL_FAILED' not in install, 'Install did not complete unambiguously')
        require(present('installed-packages'), 'Installed probe is absent')
        result['installed_apk'] = installed_hash('installed')
        nonce = secrets.token_hex(16)
        result['run_nonce'] = nonce
        output = call('instrumentation', ['shell', 'am', 'instrument', '-w', '-r',
                      '-e', 'run_nonce', nonce, '-e', 'expected_api', str(api),
                      '-e', 'expected_page_size', str(page_size), validate.COMPONENT], 90)
        result['receipt'] = validate.validate_output(output, nonce=nonce, api=api, page_size=page_size,
                                                   apk_sha256=apk_sha256, elf_sha256=elf_sha)
        result['observation_verified'] = True
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if result['initial_package_absent'] and result['installation_attempted']:
            try:
                if present('cleanup-packages'):
                    result['cleanup_apk'] = installed_hash('cleanup')
                    removed = call('uninstall', ['uninstall', validate.PACKAGE], 45)
                    require(removed == 'Success', 'Uninstall did not complete unambiguously')
                require(not present('final-packages'), 'Probe package remains after cleanup')
                result['cleanup_verified'] = True
            except Exception as error:
                result['cleanup_error'] = type(error).__name__ + ': ' + str(error)
        for path in pulled:
            if path.exists():
                path.unlink()
        if result.get('observation_verified') and result['cleanup_verified'] and 'error' not in result:
            result['status'] = 'PASS_WAEXDIAG_JNI_CONSTANTS'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--api', type=int, required=True)
    parser.add_argument('--application-page-size', type=int, required=True)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--apk-sha256', required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.adb, args.serial, args.api, args.application_page_size, args.apk,
                       args.apk_sha256, args.build_receipt, args.out)
    print(json.dumps({key: result.get(key) for key in ('status', 'cleanup_verified', 'error', 'cleanup_error')}))
    return 0 if result['status'] == 'PASS_WAEXDIAG_JNI_CONSTANTS' else 1


if __name__ == '__main__':
    sys.exit(main())
