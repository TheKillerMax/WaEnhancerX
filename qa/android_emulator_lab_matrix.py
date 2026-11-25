#!/usr/bin/env python3
"""Run one reviewed Android target with the same neutral SQLite probe APK."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets

from android_emulator_lab_pilot import (
    BootContext, GIB, invoke, main as boot_main, require, reviewed_preflight_lock,
)
from android_emulator_lab_preflight import context_check, save, sha256_file
from validate_android_sqlite_probe import PACKAGE, validate

COMPONENT = PACKAGE + '/.SqliteProbeInstrumentation'
TARGETS = {}
for _api in range(24, 38):
    _version = '37.0' if _api == 37 else str(_api)
    _tag = 'default' if _api in (27, 31, 32) else 'google_apis'
    TARGETS['api' + str(_api)] = (_api, 'system-images;android-' + _version + ';' + _tag + ';x86_64', 4096)
TARGETS['api36.1'] = (36, 'system-images;android-36.1;google_apis;x86_64', 4096)
for _label, _api, _version in (('35', 35, '35'), ('36', 36, '36'), ('36.1', 36, '36.1'),
                              ('37', 37, '37.0'), ('37.1', 37, '37.1'), ('37.2', 37, '37.2')):
    TARGETS['api' + _label + '-16k'] = (_api, 'system-images;android-' + _version + ';google_apis_ps16k;x86_64', 16384)

SOURCE_FILES = (
    'qa/android_emulator_lab_preflight.py', 'qa/android_emulator_lab_bootstrap.py',
    'qa/android_emulator_lab_pilot.py', 'qa/android_emulator_lab_matrix.py',
    'qa/summarize_android_emulator_lab_matrix.py',
    'qa/build_android_sqlite_probe.py', 'qa/validate_android_sqlite_probe.py',
    'qa/test_android_sqlite_probe.py', 'qa/ANDROID_SQLITE_PROBE.md',
    'qa/android_sqlite_probe/AndroidManifest.xml',
    'qa/android_sqlite_probe/SqliteProbeInstrumentation.java',
)


def expected_minor(target):
    label = target.removeprefix('api').removesuffix('-16k')
    return int(label.split('.')[1]) if '.' in label else 0


def checked_lock(path, target):
    lock = reviewed_preflight_lock(path)
    require(lock.get('phase') == 'extended_android_runtime_matrix', 'Wrong matrix lock phase')
    require(set(lock.get('targets', {})) == set(TARGETS), 'Lock must enumerate all 21 reviewed targets')
    for name, (api, image_path, page_size) in TARGETS.items():
        entry = lock['targets'][name]
        image = entry['image']
        require((image['path'], image['api'], image['minor'], image['abi']) ==
                (image_path, api, expected_minor(name), 'x86_64'), 'Wrong image identity for ' + name)
        require(entry['application_page_size_bytes'] == page_size, 'Wrong page-size target for ' + name)
        require(entry['minimum_free_bytes'] >= 16 * GIB, 'Initial image allowance must be at least 16 GiB')
        require(image['license_already_accepted'] is True and image['license_id'] == 'android-sdk-license' and
                image['license_text_sha1'] == '24333f8a63b6825ea9c5514f83c2829b004d1fee',
                'Image license was not already accepted in the reviewed runner')
    pilots = lock.get('boot_pilot', {})
    require(set(pilots) == {'api24', 'api35-16k'}, 'Both real pilot receipts are required')
    for name, api, pages in (('api24', 24, 4096), ('api35-16k', 35, 16384)):
        record = pilots[name]
        require(record.get('status') == 'PASS' and record.get('android_booted') is True and
                record.get('owned_emulator_reaped') is True and record.get('license_files_unchanged') is True and
                record.get('apk_installed') is False, 'Pilot is not a complete clean boot: ' + name)
        guest = record.get('guest', {})
        require((guest.get('sdk'), guest.get('abi'), guest.get('application_page_size_bytes')) ==
                (str(api), 'x86_64', str(pages)), 'Pilot guest identity differs: ' + name)
        require(re.fullmatch(r'https://github\.com/TheKillerMax/WaEnhancerX/actions/runs/\d+',
                             record.get('run_url', '')), 'Pilot run URL missing')
        require(re.fullmatch(r'[0-9a-f]{40}', record.get('head_sha', '')), 'Pilot commit SHA missing')
        for key in ('artifact_sha256', 'pilot_result_sha256', 'source_sha256'):
            require(re.fullmatch(r'[0-9a-f]{64}', record.get(key, '')), 'Pilot evidence hash missing: ' + key)
    pins = lock.get('source_sha256', {})
    require(set(pins) == set(SOURCE_FILES), 'Source pin set differs from the reviewed matrix')
    root = Path(__file__).resolve().parent.parent
    for name in SOURCE_FILES:
        source = root / name
        require(re.fullmatch(r'[0-9a-f]{64}', pins[name]) and source.is_file() and
                sha256_file(source) == pins[name], 'Matrix source changed: ' + name)
    require(target in TARGETS, 'Unknown target')
    return lock, lock['targets'][target]


def verified_probe(bundle, apk_sha256, build_receipt_sha256, lock):
    apk, receipt_path = bundle / 'sqlite-probe.apk', bundle / 'build-result.json'
    for path, expected, limit in ((apk, apk_sha256, 2 * 1024 ** 2),
                                  (receipt_path, build_receipt_sha256, 256 * 1024)):
        require(re.fullmatch(r'[0-9a-f]{64}', expected or '') and path.is_file() and
                0 < path.stat().st_size <= limit and sha256_file(path) == expected,
                'Probe producer artifact identity differs: ' + path.name)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    expected = {
        'schema': 'WAEX_SQLITE_PROBE_BUILD_V1', 'status': 'PASS_BUILD_ONLY',
        'package': PACKAGE, 'instrumentation_component': COMPONENT, 'min_sdk': 24, 'target_sdk': 36,
        'build_tools_revision': '36.0.0', 'permissions': [], 'native_libraries': [],
        'ephemeral_key_absent': True, 'runtime_tested': False,
        'phone_or_emulator_accessed': False, 'sdk_installed_or_license_accepted': False,
    }
    for key, value in expected.items():
        require(type(receipt.get(key)) is type(value) and receipt[key] == value,
                'Unexpected producer receipt field: ' + key)
    require(receipt.get('apk') == {'file': apk.name, 'bytes': apk.stat().st_size, 'sha256': apk_sha256},
            'Producer APK identity differs')
    require(receipt.get('builder_sha256') == lock['source_sha256']['qa/build_android_sqlite_probe.py'],
            'Probe builder differs from the locked source')
    expected_inputs = {name: lock['source_sha256']['qa/android_sqlite_probe/' + name]
                       for name in ('AndroidManifest.xml', 'SqliteProbeInstrumentation.java')}
    require(receipt.get('source_sha256') == expected_inputs, 'Probe input sources differ from the lock')
    require(receipt.get('sdk_metadata') == lock['build_sdk_metadata_sha256'],
            'Producer SDK metadata differs from the reviewed runner')
    require(receipt.get('tools', {}).get('java', {}).get('sha256') == lock['tool_sha256']['java'],
            'Producer Java runtime differs from the reviewed preflight')
    return apk, receipt_path, receipt


def sqlite_action(bundle, apk_sha256, build_receipt_sha256, lock):
    apk, build_receipt_path, _ = verified_probe(bundle, apk_sha256, build_receipt_sha256, lock)

    def run(context: BootContext):
        require(context.serial == 'emulator-5580' and context.guest['abi'] == 'x86_64',
                'SQLite phase requires the controller-owned x86_64 emulator')
        (context.out / 'sqlite-build-result.json').write_bytes(build_receipt_path.read_bytes())
        nonce = secrets.token_hex(16)
        phase = {'status': 'BLOCKED', 'scope': 'neutral_sqlite', 'package': PACKAGE, 'nonce': nonce,
                 'apk_sha256': apk_sha256, 'build_receipt_sha256': build_receipt_sha256,
                 'package_absent_after_cleanup': False}
        attempted = False

        def adb(name, *arguments, timeout=30):
            return invoke(context.out, name, [str(context.adb), '-s', context.serial, *arguments],
                          context.env, timeout=timeout)

        def packages(name):
            _, output = adb(name, 'shell', 'pm', 'list', 'packages', PACKAGE)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            require(lines in ([], ['package:' + PACKAGE]), 'Unexpected package-list result')
            return bool(lines)

        def installed_identity(prefix):
            _, output = adb(prefix + '-path', 'shell', 'pm', 'path', PACKAGE)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            require(len(lines) == 1 and re.fullmatch(r'package:/data/app/[A-Za-z0-9_./+~=-]+/base\.apk', lines[0]),
                    'Probe must have exactly one installed base APK')
            installed_path = lines[0].removeprefix('package:')
            require('..' not in PurePosixPath(installed_path).parts, 'Unsafe installed APK path')
            readback = context.work / (prefix + '-base.apk')
            adb(prefix + '-pull', 'pull', installed_path, str(readback), timeout=60)
            require(readback.is_file(), 'Installed APK read-back is missing')
            actual = sha256_file(readback)
            phase[prefix + '_identity'] = {'bytes': readback.stat().st_size, 'sha256': actual}
            require(actual == apk_sha256, 'Installed APK differs; a different APK will not be uninstalled')
            context.result['apk_installed'] = True
            readback.unlink()
            return actual

        try:
            require(not packages('sqlite-package-before'), 'Probe package already exists before this phase')
            attempted = True
            context.result['apk_install_attempted'] = True
            _, output = adb('sqlite-install', 'install', '-t', str(apk), timeout=90)
            require(re.search(r'^Success\s*$', output, re.M), 'Probe installation was not acknowledged')
            context.result['apk_installed'] = True
            phase['installed_apk_sha256'] = installed_identity('sqlite-installed')
            adb('sqlite-instrumentation', 'shell', 'am', 'instrument', '-w', '-r',
                '-e', 'run_nonce', nonce, COMPONENT, timeout=240)
            transcript = (context.out / 'sqlite-instrumentation.log').read_text(encoding='utf-8', errors='strict')
            receipt = validate(transcript, nonce, context.api, context.application_page_size_bytes)
            save(context.out, 'sqlite-runtime-receipt.json', receipt)
            phase.update(status='PASS', checks=receipt['checks'], sdk=receipt['sdk'],
                         application_page_size_bytes=receipt['application_page_size_bytes'],
                         sqlite_page_size_bytes=receipt['sqlite_page_size_bytes'],
                         sqlite_version=receipt['sqlite_version'],
                         runtime_receipt_sha256=sha256_file(context.out / 'sqlite-runtime-receipt.json'),
                         instrumentation_log_sha256=sha256_file(context.out / 'sqlite-instrumentation.log'))
        except Exception as exc:
            phase['execution_error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            try:
                if attempted and packages('sqlite-package-before-cleanup'):
                    installed_identity('sqlite-before-uninstall')
                    _, output = adb('sqlite-uninstall', 'uninstall', PACKAGE, timeout=60)
                    require(output.strip() == 'Success', 'Probe uninstall was not acknowledged')
                if attempted:
                    require(not packages('sqlite-package-after-cleanup'), 'Probe package remains after cleanup')
                    phase['package_absent_after_cleanup'] = True
            except Exception as exc:
                phase['status'] = 'BLOCKED'
                phase['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
                raise
            finally:
                save(context.out, 'sqlite-phase.json', phase)
        return phase

    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=sorted(TARGETS), required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--apk-dir', type=Path, required=True)
    parser.add_argument('--apk-sha256', required=True)
    parser.add_argument('--build-receipt-sha256', required=True)
    args = parser.parse_args()
    context_check(os.environ)
    lock, _ = checked_lock(args.lock, args.target)
    action = sqlite_action(args.apk_dir, args.apk_sha256, args.build_receipt_sha256, lock)
    return boot_main(['--target', args.target, '--lock', str(args.lock), '--out', str(args.out)],
                     targets=TARGETS, read_lock=checked_lock, boot_action=action,
                     phase='neutral_sqlite_matrix', result_name='matrix-result.json',
                     limits='Neutral SQLite in empty x86_64 AVDs only. No WAEX, WhatsApp, LSPosed, JNI, real ARM64 or performance-speedup claim.')


if __name__ == '__main__':
    raise SystemExit(main())
