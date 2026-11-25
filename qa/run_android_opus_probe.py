#!/usr/bin/env python3
"""Run the pinned synthetic Opus encoder only on an owned public Linux AVD."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets

from android_emulator_lab_matrix import TARGETS as MATRIX_TARGETS, checked_lock as matrix_lock, expected_minor
from android_emulator_lab_pilot import BootContext, invoke, main as boot_main, require
from android_emulator_lab_preflight import context_check, save, sha256_file
from build_android_opus_probe import COMPONENT, PACKAGE, source_pins
from validate_android_opus_probe import validate_probe

ROOT = Path(__file__).resolve().parent.parent
TARGETS = dict(MATRIX_TARGETS)
MAX_APK = 4 * 1024**2


def checked_lock(path, target):
    require(target in TARGETS, 'Only the 21 reviewed Opus matrix targets are enabled')
    return matrix_lock(path, target)


def bounded_file(path, expected_sha, limit):
    require(re.fullmatch('[a-f0-9]{64}', expected_sha or '') and path.is_file()
            and not path.is_symlink() and 0 < path.stat().st_size <= limit
            and sha256_file(path) == expected_sha, 'Producer file identity differs: ' + path.name)
    return path


def exact_fields(receipt, fields):
    for key, value in fields.items():
        require(type(receipt.get(key)) is type(value) and receipt[key] == value,
                'Unexpected producer field: ' + key)


def same_run(receipt):
    for field, variable, pattern in (('workflow_commit', 'GITHUB_SHA', '[a-f0-9]{40}'),
                                     ('run_id', 'GITHUB_RUN_ID', '[0-9]+'),
                                     ('attempt', 'GITHUB_RUN_ATTEMPT', '[1-9][0-9]*')):
        expected = os.environ.get(variable, '')
        require(re.fullmatch(pattern, expected) and receipt.get(field) == expected,
                'Producer is from another workflow commit/run/attempt: ' + field)


def verified_probe(bundle, apk_sha, receipt_sha):
    apk = bounded_file(bundle / 'opus-probe.apk', apk_sha, MAX_APK)
    receipt_path = bounded_file(bundle / 'build-result.json', receipt_sha, 1024**2)
    receipt = json.loads(receipt_path.read_bytes())
    exact_fields(receipt, {
        'schema': 'WAEX_OPUS_PROBE_BUILD_V1', 'status': 'PASS_BUILD_ONLY',
        'package': PACKAGE, 'component': COMPONENT, 'min_sdk': 24, 'target_sdk': 36,
        'permissions': [], 'native_member': 'lib/x86_64/libopuscodec.so',
        'ephemeral_key_absent': True, 'runtime_tested': False,
        'phone_or_emulator_accessed': False, 'sdk_installed_or_license_accepted': False,
    })
    same_run(receipt)
    require(receipt.get('apk') == {'file': apk.name, 'bytes': apk.stat().st_size, 'sha256': apk_sha},
            'Producer APK details differ')
    require(receipt.get('source_sha256') == source_pins(), 'Producer source differs from the current checkout')
    lock_path = ROOT / 'qa/android_opus_probe/dependency-lock.json'
    lock = json.loads(lock_path.read_bytes())
    require(receipt.get('dependency_lock_sha256') == sha256_file(lock_path)
            and receipt.get('dependencies') == lock['inputs']
            and receipt.get('native_sha256') == lock['native_sha256'], 'Producer dependency closure differs')
    commands = receipt.get('commands', [])
    names = [row.get('name') for row in commands]
    require(set(names) == {'java-version', 'javac-version', 'javac', 'd8', 'aapt2-link', 'zipalign',
                           'keytool', 'sign', 'signature-verify', 'badging', 'manifest', 'alignment'}
            and len(names) == len(set(names))
            and all(row.get('returncode') == 0 for row in commands), 'Producer command failed or duplicated')
    d8 = next(row for row in commands if row['name'] == 'd8')
    require(type(d8.get('stdout_bytes')) is int and type(d8.get('stderr_bytes')) is int
            and d8['stdout_bytes'] == 0 and d8['stderr_bytes'] == 0, 'Producer D8 diagnostics are not empty')
    return apk, receipt_path


def verified_decoder(bundle, library_sha, receipt_sha):
    library = bounded_file(bundle / 'libopus.so', library_sha, 16 * 1024**2)
    receipt_path = bounded_file(bundle / 'decoder-receipt.json', receipt_sha, 1024**2)
    receipt = json.loads(receipt_path.read_bytes())
    exact_fields(receipt, {'schema': 'WAEX_OPUS_HOST_DECODER_BUILD_V1', 'status': 'PASS_HOST_DECODER_BUILD',
                           'original_sources_unchanged': True})
    same_run(receipt)
    require(receipt.get('library') == {'name': library.name, 'bytes': library.stat().st_size,
                                       'sha256': library_sha, 'version': 'libopus 1.5.2'},
            'Host decoder library differs')
    sources = {name: sha256_file(ROOT / name) for name in (
        'qa/android_opus_probe/prepare_decoder.py', 'qa/android_opus_probe/decoder-lock.json')}
    require(receipt.get('source_sha256') == sources, 'Host decoder producer source differs')
    lock = json.loads((ROOT / 'qa/android_opus_probe/decoder-lock.json').read_bytes())
    require(receipt.get('source') == lock and receipt.get('lock_sha256') == sources[
        'qa/android_opus_probe/decoder-lock.json'], 'Host decoder release recipe differs')
    license_path = bounded_file(bundle / 'COPYING', lock['license_sha256'], 16384)
    require(receipt.get('license') == {'file': 'COPYING', 'bytes': license_path.stat().st_size,
                                       'sha256': lock['license_sha256']}, 'Decoder license differs')
    return library, receipt_path


def installed_apk_path(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    require(len(lines) == 1 and re.fullmatch(r'package:/data/app/[A-Za-z0-9_./+~=-]+/base\.apk', lines[0]),
            'Probe must have exactly one installed base APK')
    path = lines[0].removeprefix('package:')
    require('..' not in PurePosixPath(path).parts, 'Unsafe installed APK path')
    return path


def opus_action(apk, build_receipt, apk_sha, build_sha, library, decoder_receipt, library_sha, decoder_sha):
    def run(context: BootContext):
        require(context.target in TARGETS and context.serial == 'emulator-5580'
                and context.guest['abi'] == 'x86_64'
                and (context.api, context.application_page_size_bytes) ==
                    (TARGETS[context.target][0], TARGETS[context.target][2])
                and context.minor == expected_minor(context.target),
                'Opus phase requires the exact controller-owned x86_64 matrix target')
        (context.out / 'opus-build-result.json').write_bytes(build_receipt.read_bytes())
        (context.out / 'opus-decoder-receipt.json').write_bytes(decoder_receipt.read_bytes())
        nonce = secrets.token_hex(16)
        phase = {'status': 'BLOCKED', 'scope': 'synthetic_opus_120_android_encode_host_decode',
                 'package': PACKAGE, 'target': context.target, 'api': context.api,
                 'minor': context.minor, 'application_page_size_bytes': context.application_page_size_bytes,
                 'nonce': nonce, 'apk_sha256': apk_sha,
                 'build_receipt_sha256': build_sha, 'decoder_sha256': library_sha,
                 'decoder_receipt_sha256': decoder_sha, 'package_absent_after_cleanup': False,
                 'controller_sha256': sha256_file(__file__)}
        attempted = False

        def adb(name, *arguments, timeout=30, required=True):
            return invoke(context.out, name, [str(context.adb), '-s', context.serial, *arguments],
                          context.env, timeout=timeout, required=required)

        def packages(name):
            _, output = adb(name, 'shell', 'pm', 'list', 'packages', PACKAGE)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            require(lines in ([], ['package:' + PACKAGE]), 'Unexpected package-list result')
            return bool(lines)

        def installed_identity(prefix):
            _, output = adb(prefix + '-path', 'shell', 'pm', 'path', PACKAGE)
            installed_path = installed_apk_path(output)
            readback = context.work / (prefix + '-base.apk')
            require(not readback.exists(), 'Fresh installed-APK readback destination required')
            pull, output = adb(prefix + '-pull', 'pull', installed_path, str(readback),
                               timeout=60, required=False)
            require(pull['failure'] is None, 'Installed APK pull was interrupted or exceeded its bound')
            method = 'adb_pull'
            if pull['returncode'] != 0:
                # Preserve the independently reviewed SQLite API24 readback condition.
                # STATv1 cannot convey errno; its text alone does not prove absence.
                require(context.api == 24 and context.application_page_size_bytes == 4096
                        and pull['returncode'] == 1 and not readback.exists()
                        and output.strip() == "adb: error: remote object '" + installed_path + "' does not exist"
                        and re.fullmatch(r'/data/app/' + re.escape(PACKAGE) + r'-[A-Za-z0-9_-]+/base\.apk',
                                         installed_path),
                        'Installed APK pull failed without the reviewed API24 readback condition')
                name = prefix + '-exec-out'
                command, _ = adb(name, 'exec-out', '/system/bin/cat', installed_path,
                                 timeout=60, required=False)
                readback = context.out / (name + '.log')
                require(command['failure'] is None and command['returncode'] == 0,
                        'API24 binary APK readback failed')
                method = 'adb_exec_out_cat_api24'
            bounded_file(readback, apk_sha, MAX_APK)
            require(readback.stat().st_size == apk.stat().st_size, 'Installed APK size differs')
            identity = {'bytes': readback.stat().st_size, 'sha256': sha256_file(readback), 'method': method}
            phase[prefix + '_identity'] = identity
            readback.unlink()
            return identity

        try:
            _, qemu = adb('opus-guest-emulator', 'shell', 'getprop', 'ro.kernel.qemu')
            _, uid = adb('opus-shell-uid', 'shell', 'id', '-u')
            require(qemu.strip() == '1' and uid.strip() == '2000', 'Expected unprivileged emulator shell')
            require(not packages('opus-package-before'), 'Probe package already exists')
            bounded_file(apk, apk_sha, MAX_APK)
            attempted = True
            context.result['apk_install_attempted'] = True
            _, output = adb('opus-install', 'install', '-t', str(apk), timeout=90)
            require(re.search(r'^Success\s*$', output, re.M), 'Probe installation was not acknowledged')
            context.result['apk_installed'] = True
            installed_identity('opus-installed')
            adb('opus-instrumentation', 'shell', 'am', 'instrument', '-w', '-r',
                '-e', 'run_nonce', nonce, COMPONENT, timeout=120)
            log = context.out / 'opus-instrumentation.log'
            require(log.stat().st_size <= 4 * 1024**2, 'Opus instrumentation log exceeds 4 MiB')
            report, payloads = validate_probe(log.read_bytes(), nonce, context.api,
                                              context.application_page_size_bytes, library, library_sha,
                                              expected_minor=context.minor)
            for name, raw in payloads.items():
                require(name in ('pcm48k', 'pcm16k'), 'Unexpected encoded case')
                (context.out / (name + '.ogg')).write_bytes(raw)
            save(context.out, 'opus-validation.json', report)
            phase.update(checks=report['android_receipt']['checks'],
                         jni_calls=report['transport']['jni_calls'],
                         runtime_receipt_sha256=sha256_file(context.out / 'opus-validation.json'),
                         instrumentation_log_sha256=sha256_file(log))
        except Exception as exc:
            phase['execution_error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            try:
                if attempted and packages('opus-package-before-cleanup'):
                    installed_identity('opus-before-uninstall')
                    _, output = adb('opus-uninstall', 'uninstall', PACKAGE, timeout=60)
                    require(output.strip() == 'Success', 'Probe uninstall was not acknowledged')
                if attempted:
                    require(not packages('opus-package-after-cleanup'), 'Probe package remains after cleanup')
                    phase['package_absent_after_cleanup'] = True
            except Exception as exc:
                phase['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
            if not phase.get('execution_error') and not phase.get('cleanup_error') \
                    and phase['package_absent_after_cleanup'] and phase.get('runtime_receipt_sha256'):
                phase['status'] = 'PASS'
            save(context.out, 'opus-phase.json', phase)
        require(phase['status'] == 'PASS', 'Opus phase blocked: ' +
                '; '.join(phase[key] for key in ('execution_error', 'cleanup_error') if key in phase))
        return phase
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=sorted(TARGETS), required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--apk-sha256', required=True)
    parser.add_argument('--build-receipt-sha256', required=True)
    parser.add_argument('--decoder', type=Path, required=True)
    parser.add_argument('--decoder-sha256', required=True)
    parser.add_argument('--decoder-receipt-sha256', required=True)
    args = parser.parse_args()
    context_check(os.environ)
    checked_lock(args.lock, args.target)
    apk, build_receipt = verified_probe(args.artifact, args.apk_sha256, args.build_receipt_sha256)
    library, decoder_receipt = verified_decoder(args.decoder, args.decoder_sha256, args.decoder_receipt_sha256)
    action = opus_action(apk, build_receipt, args.apk_sha256, args.build_receipt_sha256,
                         library, decoder_receipt, args.decoder_sha256, args.decoder_receipt_sha256)
    return boot_main(['--target', args.target, '--lock', str(args.lock), '--out', str(args.out)],
                     targets=TARGETS, read_lock=checked_lock, boot_action=action,
                     phase='neutral_opus_matrix', result_name='opus-result.json',
                     limits='Synthetic mono Opus1.2.0 JNI encoding on x86_64 AVDs, with independent host '
                            'Ogg validation/decoding. No WAEX, WhatsApp, LSPosed, playback, physical ARM64, '
                            'full native lifecycle or production dependency qualification.')


if __name__ == '__main__':
    raise SystemExit(main())
