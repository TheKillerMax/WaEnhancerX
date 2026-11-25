#!/usr/bin/env python3
"""Require both current-run, fully cleaned JNI constant observations from the same producer."""
import argparse
import json
import os
from pathlib import Path
import re

from android_native_constants_lab import TARGETS, PROBE_PINS, LIMITS, checked_lock
from android_emulator_lab_pilot import guest_version_identity
from android_emulator_lab_preflight import context_check, save, sha256_file
from summarize_android_emulator_lab_matrix import verify_manifest
import validate_native_constants_probe as validate

require = validate.require


def validate_row(path, lock, lock_sha, run_id, attempt, head, apk_sha, build_sha):
    manifest_count = verify_manifest(path.parent)
    result = validate.strict_json(path.read_text(encoding='utf-8'))
    target = result.get('target')
    require(target in TARGETS, 'Unexpected JNI target')
    expected = {'status': 'PASS', 'phase': 'waexdiag_jni_constants', 'android_booted': True,
                'requested_phase_completed': True, 'owned_emulator_reaped': True,
                'license_files_unchanged': True, 'apk_install_attempted': True, 'apk_installed': True,
                'licenses_accepted_by_this_run': False, 'github_run_id': run_id,
                'github_run_attempt': attempt, 'github_head_sha': head, 'lock_sha256': lock_sha,
                'source_sha256': lock['source_sha256']['qa/android_emulator_lab_pilot.py'], 'issues': []}
    for key, value in expected.items():
        require(type(result.get(key)) is type(value) and result[key] == value, 'Runtime result: ' + key)
    entry = lock['targets'][target]
    guest = result['guest']
    require(guest.get('abi') == 'x86_64'
            and guest.get('application_page_size_bytes') == str(TARGETS[target][2]), 'Guest ABI/page mismatch')
    require(result['guest_version'] == guest_version_identity(guest, entry['image']), 'Guest version mismatch')
    phase_path = path.parent / 'native-constants-phase.json'
    phase = validate.strict_json(phase_path.read_text(encoding='utf-8'))
    require(phase == result['phase_receipt'] and phase['status'] == 'PASS' and phase['scope'] == validate.SCOPE
            and phase['target'] == target and phase['package_absent_after_cleanup'] is True,
            'Native phase is incomplete or differs from controller')
    require(phase['apk_sha256'] == apk_sha and phase['build_receipt_sha256'] == build_sha,
            'Producer APK/receipt identity differs')
    build_path = path.parent / 'native-build-result.json'
    require(sha256_file(build_path) == build_sha, 'Copied build receipt SHA mismatch')
    build = validate.strict_json(build_path.read_text(encoding='utf-8'))
    require(build['status'] == 'PASS_BUILD_ONLY' and build['input_files'] == PROBE_PINS
            and build['apk']['apk_sha256'] == apk_sha and build['ephemeral_key_absent'] is True
            and build['license_registry_unchanged'] is True, 'Producer is incomplete')
    probe_dir = path.parent / 'native-probe'
    observed = validate.strict_json((probe_dir / 'result.json').read_text(encoding='utf-8'))
    require(observed == phase['probe'] and observed['status'] == 'PASS_WAEXDIAG_JNI_CONSTANTS'
            and observed['cleanup_verified'] is True and observed['initial_package_absent'] is True,
            'Specific JNI receipt differs or cleanup is incomplete')
    require(observed['installed_apk']['sha256'] == apk_sha and observed['cleanup_apk']['sha256'] == apk_sha,
            'Installed/cleanup APK identities differ')
    logs = [p for p in probe_dir.iterdir() if re.fullmatch(r'\d+-instrumentation\.log', p.name)]
    require(len(logs) == 1, 'Expected one instrumentation log')
    receipt = validate.validate_output(logs[0].read_text(encoding='utf-8'), nonce=phase['nonce'],
                                      api=TARGETS[target][0], page_size=TARGETS[target][2],
                                      apk_sha256=apk_sha, elf_sha256=build['native']['elf_sha256'])
    require(receipt == observed['receipt'] and phase['jni_calls'] == 14 and phase['strings_checked'] == 38
            and phase['native_elf_sha256'] == receipt['bundled_elf_sha256'], 'Runtime oracle/phase mismatch')
    return {'target': target, 'status': 'PASS', 'api': TARGETS[target][0], 'minor': 0,
            'image_path': TARGETS[target][1], 'application_page_size_bytes': TARGETS[target][2],
            'jni_calls': 14, 'strings_checked': 38, 'apk_sha256': apk_sha,
            'elf_sha256': receipt['bundled_elf_sha256'], 'run_nonce': phase['nonce'],
            'runtime_result_sha256': sha256_file(path), 'manifest_files_verified': manifest_count}


def matrix_status(rows, issues):
    return ('PASS_TWO_WAEXDIAG_PAGE_ENVIRONMENTS'
            if not issues and set(rows) == set(TARGETS) and all(row['status'] == 'PASS' for row in rows.values())
            else 'BLOCKED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--apk-sha256', required=True)
    parser.add_argument('--build-receipt-sha256', required=True)
    parser.add_argument('--build-job-result', required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'BLOCKED', 'expected_targets': sorted(TARGETS), 'rows': {}, 'issues': [],
              'full_waex_tested': False, 'other_elf_tested': False, 'real_arm64_16k_validated': False,
              'returned_commands_executed': False, 'limits': LIMITS}
    try:
        context_check(os.environ)
        lock, _ = checked_lock(args.lock, 'api35')
        require(args.build_job_result == 'success', 'Single producer job did not succeed')
        require(re.fullmatch('[0-9a-f]{64}', args.apk_sha256)
                and re.fullmatch('[0-9a-f]{64}', args.build_receipt_sha256), 'Missing producer hashes')
        run_id, attempt, head = (os.environ[key] for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
        report.update(apk_sha256=args.apk_sha256, build_receipt_sha256=args.build_receipt_sha256,
                      github_run_id=run_id, github_run_attempt=attempt, github_head_sha=head)
        seen = set()
        for path in sorted(args.reports.rglob('native-result.json')):
            try:
                target = validate.strict_json(path.read_text())['target']
                require(target in TARGETS and target not in seen, 'Duplicate/unexpected target')
                seen.add(target)
                row = validate_row(path, lock, sha256_file(args.lock), run_id, attempt, head,
                                   args.apk_sha256, args.build_receipt_sha256)
                artifact = args.reports / path.relative_to(args.reports).parts[0]
                bootstraps = list(artifact.rglob('bootstrap-result.json'))
                require(len(bootstraps) == 1, 'Exactly one bootstrap receipt per target is required')
                verify_manifest(bootstraps[0].parent)
                bootstrap = validate.strict_json(bootstraps[0].read_text())
                require(bootstrap['status'] == 'PASS' and bootstrap['license_files_unchanged'] is True
                        and bootstrap['source_sha256'] == lock['source_sha256']['qa/android_emulator_lab_bootstrap.py'],
                        'Bootstrap receipt is incomplete')
                report['rows'][target] = row
            except Exception as error:
                report['issues'].append(str(path.relative_to(args.reports)) + ': ' + str(error))
        for target in TARGETS:
            if target not in report['rows']:
                report['rows'][target] = {'target': target, 'status': 'MISSING'}
                report['issues'].append('Missing complete target: ' + target)
        nonces = [row['run_nonce'] for row in report['rows'].values() if row['status'] == 'PASS']
        require(len(nonces) == len(set(nonces)), 'Targets reused the same nonce')
    except Exception as error:
        report['issues'].append(type(error).__name__ + ': ' + str(error))
    report['status'] = matrix_status(report['rows'], report['issues'])
    save(args.out, 'native-summary.json', report)
    lines = ['# waexdiag JNI constants: two application page environments', '', '**' + report['status'] + '**', '',
             '| Target | Result | Application page bytes | JNI calls | Strings |',
             '| --- | --- | ---: | ---: | ---: |']
    for name in sorted(TARGETS):
        row = report['rows'].get(name, {'status': 'MISSING'})
        lines.append('| ' + name + ' | ' + row['status'] + ' | ' + str(TARGETS[name][2]) + ' | '
                     + str(row.get('jni_calls', 0)) + ' | ' + str(row.get('strings_checked', 0)) + ' |')
    lines += ['', LIMITS, '']
    (args.out / 'native-summary.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'issues': report['issues']}))
    return 0 if report['status'].startswith('PASS_TWO_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
