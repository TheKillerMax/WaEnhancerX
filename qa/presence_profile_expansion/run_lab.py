#!/usr/bin/env python3
"""Attach the pinned ART pixel probe to the shared fresh-AVD controller."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

from presence_profile_expansion.pilot import main as boot_main, invoke, require
from android_emulator_lab_matrix import TARGETS, checked_lock as matrix_lock, expected_minor
from presence_profile_expansion.build_lab import (LOCK, SOURCE, PACKAGE, checked_lock, digest, save, verify_files,
                                    validate_toolchain_receipt, validate_d8_receipt)
from presence_profile_expansion.probe.run_presence_art_probe import verified_process_page_size
from presence_profile_expansion.identity import verified_process_identity
from presence_profile_expansion.guard import context_check, TARGET_NAMES

ART_TARGETS = {name: TARGETS[name] for name in TARGET_NAMES}
LIMITS = ('Four original/neutral ART Canvas cases and seven PNG observations per reviewed x86_64 profile. '
          'Only the fifteen new locked profiles; 16 KiB targets are x86_64 simulations. '
          'No full WAEX APK, Xposed, WhatsApp, DSU, physical ARM64 or private dependencies.')


def validate_boot_context(ctx, target):
    expected = ART_TARGETS.get(target)
    require(expected is not None and ctx.target == target and type(ctx.api) is int
            and type(ctx.minor) is int and type(ctx.application_page_size_bytes) is int
            and ctx.api == expected[0]
            and ctx.minor == expected_minor(target) and ctx.application_page_size_bytes == expected[2]
            and ctx.serial == 'emulator-5580' and ctx.guest.get('abi') == 'x86_64'
            and ctx.guest.get('sdk') == str(expected[0])
            and ctx.guest.get('application_page_size_bytes') == str(expected[2]),
            'Unexpected ART boot context')


def verify_artifact(folder, expected_sha):
    require(re.fullmatch(r'[a-f0-9]{64}', expected_sha or ''), 'Independent build job APK hash required')
    require({p.name for p in folder.iterdir()} == {'presence-art-positive.apk', 'artifact-manifest.json'},
            'Unexpected artifact file set')
    apk = folder / 'presence-art-positive.apk'
    manifest = folder / 'artifact-manifest.json'
    require(not apk.is_symlink() and not manifest.is_symlink(), 'Artifact symlink rejected')
    value = json.loads(manifest.read_text(encoding='utf-8'))
    lock = checked_lock()
    require(value['schema'] == 'WAEX_PRESENCE_PROFILE_BUILD_V1' and value['status'] == 'PASS_BUILD_ONLY'
            and value['source_revision'] == SOURCE
            and value.get('probe_origin_revision') == lock['probe_origin_revision']
            and value['probe_revision'] == value['workflow_commit']
            and value['workflow_commit'] == os.environ.get('GITHUB_SHA')
            and re.fullmatch(r'[0-9]+', value['run_id'] or '')
            and re.fullmatch(r'[1-9][0-9]*', value['attempt'] or '')
            and value['run_id'] == os.environ.get('GITHUB_RUN_ID')
            and value['attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT')
            and value['lock_sha256'] == digest(LOCK)
            and value['renderer_harness_sha256'] == lock['renderer_harness_sha256'],
            'Artifact provenance differs')
    require(value['builder_sha256'] == digest(Path(__file__).with_name('build_lab.py'))
            and value['toolchain_source_sha256'] == lock['toolchain_source_sha256'],
            'Artifact compiler/builder provenance differs')
    require(value.get('producer_identity') == {'workflow_commit': value['workflow_commit'],
            'run_id': value['run_id'], 'attempt': value['attempt']}, 'Embedded producer receipt differs')
    validate_toolchain_receipt(value['kotlin_toolchain'])
    validate_d8_receipt(value['d8_diagnostics'])
    require(value['package'] == PACKAGE and value['expected_tests'] == 4
            and value['min_sdk'] == 24 and value['target_sdk'] == 28
            and value['installed'] is False and value['art_execution'] == 'NOT_RUN'
            and value['ephemeral_key_absent'] is True, 'Artifact build scope differs')
    require(digest(apk) == expected_sha == value['apk']['sha256']
            and apk.stat().st_size == value['apk']['bytes']
            and 0 < apk.stat().st_size < 2 * 1024**2, 'Artifact APK identity differs')
    return apk, value


def validate_receipt(receipt, api, expected_sha, directory, page_bytes, target, minor, boot, built):
    require(receipt.get('page_size_verified') is True
            and type(receipt.get('application_page_size_bytes')) is int
            and type(receipt.get('expected_application_page_size_bytes')) is int
            and receipt['application_page_size_bytes'] == receipt['expected_application_page_size_bytes'] == page_bytes,
            'ART receipt process page size differs')
    report = json.loads((directory / 'device-result.json').read_bytes())
    verified_process_page_size(report, page_bytes)
    require(receipt.get('schema') == 'WAEX_PRESENCE_PROFILE_RECEIPT_V1'
            and receipt.get('target') == target and type(receipt.get('minor')) is int
            and receipt['minor'] == minor and receipt.get('process_identity_verified') is True
            and receipt.get('boot_identity_verified') is True, 'New process/boot receipt is incomplete')
    expected_contract = {'target': target, 'api': api, 'minor': minor, 'page_bytes': page_bytes,
            'nonce': receipt['nonce'], 'run_id': receipt['run_id'], 'boot_id': boot,
            'producer_commit': built['workflow_commit'], 'github_run_id': built['run_id'],
            'github_run_attempt': built['attempt'], 'apk_sha256': expected_sha,
            'apk_bytes': built['apk']['bytes'], 'installed_path': receipt['readbacks']['installed']['path']}
    require(receipt.get('identity_contract') == expected_contract
            and receipt.get('process_identity') == report.get('process_identity'),
            'Process identity is detached from this build/target/boot')
    verified_process_identity(report, expected_contract)
    expected_boot_reads={'boot-before-install','boot-install-gate','boot-instrument-gate',
                         'boot-after-instrument','boot-before-cleanup','boot-after-cleanup'}
    require(set(receipt.get('boot_readbacks', {})) == expected_boot_reads
            and all(value == boot for value in receipt['boot_readbacks'].values()), 'Kernel boot changed during the attempt')
    for name in expected_boot_reads:
        raw = (directory / (name + '.stdout')).read_bytes()
        require(0 < len(raw) <= 128 and raw.decode('ascii').strip() == boot
                and not (directory / (name + '.stderr')).read_bytes().strip(), 'Raw boot readback differs')
    require(receipt['status'] == 'PASS' and receipt['failure'] is None
            and receipt['api'] == api and receipt['serial'] == 'emulator-5580'
            and receipt['apk_sha256'] == receipt['installed_apk_sha256'] == expected_sha
            and receipt['initially_absent'] is True, 'ART launcher receipt failed')
    require(receipt['cleanup']['status'] == 'PASS' and receipt['cleanup']['verified_absent'] is True
            and receipt['instrumentation_finish_verified'] is True
            and receipt['all_seven_png_phases_present'] is True, 'ART finish/phases/cleanup incomplete')
    cleanup = receipt['cleanup']
    require(cleanup.get('identity_verified') is True and cleanup.get('apk_sha256') == expected_sha
            and cleanup.get('package') == PACKAGE, 'Cleanup lacked a fresh matching APK identity')
    readbacks = receipt.get('readbacks', {})
    require(set(readbacks) == {'installed', 'cleanup-installed'}, 'Both installed APK readbacks required')
    for identity in readbacks.values():
        require(identity.get('sha256') == expected_sha and identity.get('matches_producer') is True
                and type(identity.get('bytes')) is int and 0 < identity['bytes'] <= 2 * 1024**2
                and identity.get('method') in ('adb_pull', 'adb_exec_out_cat_api24'),
                'Readback identity/method differs')
        require(identity['method'] != 'adb_exec_out_cat_api24' or api == 24, 'Legacy fallback escaped API24')
    require(readbacks['installed']['bytes'] == readbacks['cleanup-installed']['bytes'] == cleanup.get('apk_bytes'),
            'Readback lengths differ')
    require(receipt['device_counts'] == {'tests': 4, 'passed': 4, 'failures': 0, 'errors': 0, 'skipped': 0},
            'ART cases did not all pass')
    pngs = receipt['png_sha256']
    require(len(pngs) == 7 and set(pngs) == {p.name for p in directory.glob('*.png')},
            'Seven exact PNG evidence files required')
    for name, expected in pngs.items():
        require(re.fullmatch(r'[A-Za-z0-9_-]+\.png', name) and digest(directory / name) == expected,
                'PNG identity differs')
        require((directory / name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'PNG signature differs')
    require(digest(directory / 'device-result.json') == receipt['device_result_sha256'],
            'Device JSON identity differs')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=sorted(ART_TARGETS), required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--apk-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    context_check(os.environ)
    apk, built = verify_artifact(args.artifact.resolve(), args.apk_sha256)
    verify_files(Path(__file__).resolve().parents[2], checked_lock()['probe_sources'])

    def after_boot(ctx):
        validate_boot_context(ctx, args.target)
        _, boot_text = invoke(ctx.out, 'presence-kernel-boot-id',
            [str(ctx.adb), '-s', ctx.serial, 'shell', 'cat', '/proc/sys/kernel/random/boot_id'], ctx.env)
        boot = boot_text.strip()
        require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot), 'Concrete kernel boot UUID required')
        report_dir = ctx.out / 'presence'
        launcher = Path(__file__).with_name('probe') / 'run_presence_art_probe.py'
        command = [sys.executable, str(launcher), '--adb', str(ctx.adb),
                   '--serial', ctx.serial, '--api', str(ctx.api), '--apk', str(apk),
                   '--page-bytes', str(ctx.application_page_size_bytes),
                   '--expected-sha256', args.apk_sha256, '--out', str(report_dir),
                   '--target', args.target, '--minor', str(ctx.minor), '--expected-boot-id', boot,
                   '--producer-commit', built['workflow_commit'], '--github-run-id', built['run_id'],
                   '--github-run-attempt', built['attempt']]
        outcome, _ = invoke(ctx.out, 'presence-art-launcher', command, ctx.env, timeout=420, required=False)
        receipt_path = report_dir / 'receipt.json'
        require(receipt_path.is_file(), 'ART launcher did not emit its final receipt')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        attempted = any(row.get('name') == 'install' for row in receipt['commands'])
        ctx.result['apk_install_attempted'] = attempted
        ctx.result['apk_installed'] = receipt.get('installed_apk_sha256') == args.apk_sha256
        readbacks = []
        for name in ('installed.apk', 'ambiguous-installed.apk', 'cleanup-installed.apk'):
            path = report_dir / name
            if path.is_file():
                row = {'name': name, 'bytes': path.stat().st_size, 'sha256': digest(path)}
                row['matches_built_apk'] = row['sha256'] == args.apk_sha256
                if row['matches_built_apk']:
                    path.unlink(); row['action'] = 'removed_redundant_verified_qa_apk'
                else:
                    quarantine = ctx.work / 'unuploaded-readbacks'; quarantine.mkdir(exist_ok=True)
                    path.replace(quarantine / name); row['action'] = 'preserved_outside_reports'
                readbacks.append(row)
        save(report_dir / 'apk-readback-identities.json', readbacks)
        save(report_dir / 'build-artifact-provenance.json', built)
        require(outcome['failure'] is None and outcome['returncode'] == 0, 'ART launcher failed')
        validate_receipt(receipt, ctx.api, args.apk_sha256, report_dir, ctx.application_page_size_bytes,
                         args.target, ctx.minor, boot, built)
        return {'status': 'PASS', 'tests': 4, 'png_count': 7, 'package': PACKAGE,
                'application_page_size_bytes': receipt['application_page_size_bytes'],
                'process_page_size_verified': True, 'process_identity_verified': True,
                'process_identity': receipt['process_identity'], 'boot_identity_verified': True,
                'kernel_boot_id': boot, 'nonce': receipt['nonce'],
                'apk_sha256': args.apk_sha256, 'receipt_sha256': digest(receipt_path),
                'scope': LIMITS}

    return boot_main(['--target', args.target, '--lock', str(args.lock), '--out', str(args.out)],
                     targets=ART_TARGETS, read_lock=matrix_lock, boot_action=after_boot,
                     phase='presence_profile_expansion', result_name='presence-profile-result.json', limits=LIMITS)


if __name__ == '__main__':
    raise SystemExit(main())
