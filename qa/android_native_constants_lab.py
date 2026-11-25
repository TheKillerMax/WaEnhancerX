#!/usr/bin/env python3
"""Run the same isolated JNI constants APK in the two reviewed API35 page environments."""
import argparse
import json
import os
from pathlib import Path
import re

import android_emulator_lab_matrix as matrix
from android_emulator_lab_pilot import BootContext, main as boot_main
from android_emulator_lab_preflight import context_check, save, sha256_file
import run_native_constants_probe as probe
import validate_native_constants_probe as validate

TARGETS = {
    'api35': (35, 'system-images;android-35;google_apis;x86_64', 4096),
    'api35-16k': (35, 'system-images;android-35;google_apis_ps16k;x86_64', 16384),
}
PROBE_PINS = {
    'build_native_constants_probe.py': {'bytes': 16269, 'sha256': 'b5e164bf7c459c85ca9633972dc367dfbbd5b2550e47487aaf8ecf647be44b75'},
    'run_native_constants_probe.py': {'bytes': 8637, 'sha256': 'f088c94301c8834094ad4849a09396edb554aea99fd749975384a1b66b8f6552'},
    'validate_native_constants_probe.py': {'bytes': 7837, 'sha256': '61c8b3e9040809a94e7d0971e26b8a88e51cbfc71cf0d8de0b7aacb95978bf71'},
    'test_native_constants_probe.py': {'bytes': 14667, 'sha256': '0a81f045da9832c0e17bb149117dae42fec69675e1aaba4ff90611654bc19be7'},
    'NATIVE_CONSTANTS_PROBE.md': {'bytes': 5220, 'sha256': 'a2cf9d99c00ff78aa2aa4057f88575b35cbf7c5f5f237e1fc883525aa710d274'},
    'native_constants_probe/AndroidManifest.xml': {'bytes': 655, 'sha256': 'f897899342bee012408cb587374dc7ec5b255a1c97d0efaa309e780cc17be91f'},
    'native_constants_probe/NativeDiagPaths.java': {'bytes': 975, 'sha256': '2e724e4394df928eef316621a8af490f1a639543ffdd4e3bfcfa6e00f82e0bb9'},
    'native_constants_probe/NativeConstantsInstrumentation.java': {'bytes': 10074, 'sha256': 'b5a6dc74480f5617d7116613d6adffa24c3aeecf82ff98a809d4c319400f90a4'},
    'native_constants_probe/expected_constants.json': {'bytes': 4214, 'sha256': validate.CONTRACT_SHA256},
}
require = validate.require
LIMITS = ('Only reviewed waexdiag x86_64 loading and 14 constant-return JNI methods; '
          'one identical APK in API35 4K and simulated16K application page environments. '
          'No returned command/path is used, no other ELF/full WAEX/WhatsApp/LSPosed/root or real ARM64 coverage.')


def checked_lock(path, target):
    require(target in TARGETS and TARGETS[target] == matrix.TARGETS[target], 'JNI target differs from the matrix')
    require(validate.source_inventory() == PROBE_PINS, 'Reviewed JNI source pins changed')
    lock, entry = matrix.checked_lock(path, target)
    require(entry['image']['minor'] == 0 and entry['application_page_size_bytes'] == TARGETS[target][2],
            'Unexpected target minor/page identity')
    return lock, entry


def verified_bundle(bundle, apk_sha256, build_receipt_sha256, lock):
    bundle = Path(bundle)
    apk, receipt_path = bundle / 'native-constants-probe.apk', bundle / 'build-result.json'
    for path, expected, maximum in ((apk, apk_sha256, 8 * 1024**2),
                                     (receipt_path, build_receipt_sha256, 1024**2)):
        require(re.fullmatch('[0-9a-f]{64}', expected or '') and path.is_file()
                and 0 < path.stat().st_size <= maximum and sha256_file(path) == expected,
                'Producer artifact identity differs: ' + path.name)
    build = validate.strict_json(receipt_path.read_text(encoding='utf-8'))
    expected = {'schema': 'WAEXDIAG_PROBE_BUILD_V2', 'status': 'PASS_BUILD_ONLY',
                'scope': validate.SCOPE, 'package': validate.PACKAGE,
                'source_revision': validate.SOURCE_REVISION, 'source_sha256': validate.SOURCE_SHA256,
                'cmake_sha256': validate.CMAKE_SHA256, 'contract_sha256': validate.CONTRACT_SHA256,
                'ephemeral_key_absent': True, 'license_registry_unchanged': True,
                'licenses_accepted_by_this_run': False, 'jni_executed': False, 'android_booted': False}
    for key, value in expected.items():
        require(type(build.get(key)) is type(value) and build[key] == value, 'Producer receipt: ' + key)
    require(build['input_files'] == PROBE_PINS == validate.source_inventory(), 'Producer sources differ')
    require(build['tools']['java']['sha256'] == lock['tool_sha256']['java'], 'Producer Java differs from reviewed preflight')
    native = build['native']
    require(native['abi'] == 'x86_64' and native['api'] == 24 and native['elf']['issues'] == []
            and native['elf']['relro_segments'] and len(native['jni_exports']) == 14, 'Native build receipt is incomplete')
    inventory = validate.inspect_apk(apk, apk_sha256, native['elf_sha256'])
    require(inventory == build['apk'], 'Producer APK inventory differs')
    return apk, receipt_path, build


def native_action(bundle, apk_sha256, build_receipt_sha256, lock):
    apk, receipt_path, build = verified_bundle(bundle, apk_sha256, build_receipt_sha256, lock)

    def run(context: BootContext):
        phase = {'status': 'BLOCKED', 'scope': validate.SCOPE, 'package': validate.PACKAGE,
                 'target': context.target, 'apk_sha256': apk_sha256,
                 'build_receipt_sha256': build_receipt_sha256, 'package_absent_after_cleanup': False}
        try:
            require(context.target in TARGETS and context.serial == validate.SERIAL, 'Unassigned native AVD')
            api, image_path, pages = TARGETS[context.target]
            require(context.api == api and context.minor == 0 and context.application_page_size_bytes == pages,
                    'Boot context differs from reviewed target')
            require(context.entry['image']['path'] == image_path and context.guest['sdk'] == str(api)
                    and context.guest['abi'] == 'x86_64'
                    and context.guest['application_page_size_bytes'] == str(pages), 'Guest observation mismatch')
            copied = context.out / 'native-build-result.json'
            require(not copied.exists(), 'Build receipt destination must be new')
            copied.write_bytes(receipt_path.read_bytes())
            observed = probe.run_probe(context.adb, context.serial, context.api, pages, apk, apk_sha256,
                                       receipt_path, context.out / 'native-probe', env=context.env)
            context.result['apk_install_attempted'] = observed['installation_attempted']
            context.result['apk_installed'] = 'installed_apk' in observed
            phase['probe'] = observed
            require(observed['status'] == 'PASS_WAEXDIAG_JNI_CONSTANTS' and observed['cleanup_verified'] is True,
                    'JNI probe did not complete observation and cleanup')
            phase.update(status='PASS', package_absent_after_cleanup=True, jni_calls=14, strings_checked=38,
                         native_elf_sha256=build['native']['elf_sha256'],
                         application_page_size_bytes=pages, nonce=observed['run_nonce'])
        except Exception as error:
            phase['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            save(context.out, 'native-constants-phase.json', phase)
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
    action = native_action(args.apk_dir, args.apk_sha256, args.build_receipt_sha256, lock)
    return boot_main(['--target', args.target, '--lock', str(args.lock), '--out', str(args.out)],
                     targets=TARGETS, read_lock=checked_lock, boot_action=action,
                     phase='waexdiag_jni_constants', result_name='native-result.json', limits=LIMITS)


if __name__ == '__main__':
    raise SystemExit(main())
