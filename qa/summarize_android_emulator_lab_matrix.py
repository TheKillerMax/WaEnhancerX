#!/usr/bin/env python3
"""Fail closed unless all 21 current-run SQLite target receipts are complete."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re

from android_emulator_lab_matrix import TARGETS, checked_lock
from android_emulator_lab_pilot import guest_version_identity, require, validate_guest_readiness
from android_emulator_lab_preflight import context_check, save, sha256_file
from validate_android_sqlite_probe import validate


def verify_manifest(directory):
    path = directory / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(manifest, dict) and manifest, 'Missing report manifest')
    for relative, identity in manifest.items():
        name = PurePosixPath(relative)
        require(relative and not name.is_absolute() and '..' not in name.parts and '\\' not in relative and
                name.as_posix() == relative and relative != 'manifest.json', 'Unsafe manifest member')
        member = directory.joinpath(*name.parts)
        require(not member.is_symlink() and directory.resolve() in member.resolve().parents and member.is_file(),
                'Missing or escaped manifest member: ' + relative)
        require(type(identity.get('bytes')) is int and identity['bytes'] == member.stat().st_size and
                re.fullmatch(r'[0-9a-f]{64}', identity.get('sha256', '')) and
                sha256_file(member) == identity['sha256'], 'Manifest hash/size mismatch: ' + relative)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*')
              if p.is_file() and p != path}
    require(actual == set(manifest), 'Manifest does not cover the complete report directory')
    return len(manifest)


def validate_row(path, lock, lock_sha, run_id, attempt, head, apk_sha, build_sha):
    count = verify_manifest(path.parent)
    result = json.loads(path.read_text(encoding='utf-8'))
    target = result.get('target')
    require(target in TARGETS, 'Unexpected target receipt')
    expected = {
        'status': 'PASS', 'phase': 'neutral_sqlite_matrix', 'android_booted': True,
        'requested_phase_completed': True, 'owned_emulator_reaped': True,
        'license_files_unchanged': True, 'apk_install_attempted': True, 'apk_installed': True,
        'licenses_accepted_by_this_run': False, 'github_run_id': run_id,
        'github_run_attempt': attempt, 'github_head_sha': head, 'lock_sha256': lock_sha,
        'source_sha256': lock['source_sha256']['qa/android_emulator_lab_pilot.py'], 'issues': [],
    }
    for key, value in expected.items():
        require(type(result.get(key)) is type(value) and result[key] == value,
                'Target result mismatch: ' + key)
    entry = lock['targets'][target]
    if entry['image']['api'] >= 36:
        ready = json.loads((path.parent / 'guest-readiness.json').read_text(encoding='utf-8'))
        require(result.get('guest_readiness') == ready, 'Readiness receipt differs from controller')
        validate_guest_readiness(ready)
    guest = result['guest']
    require(guest.get('abi') == 'x86_64' and
            guest.get('application_page_size_bytes') == str(entry['application_page_size_bytes']),
            'Wrong guest ABI/page size')
    version = guest_version_identity(guest, entry['image'])
    require(result.get('guest_version') == version, 'Version observation differs from guest metadata')
    phase = json.loads((path.parent / 'sqlite-phase.json').read_text(encoding='utf-8'))
    require(phase == result.get('phase_receipt'), 'Phase receipt differs from the controller result')
    require(phase.get('status') == 'PASS' and phase.get('scope') == 'neutral_sqlite' and
            phase.get('package_absent_after_cleanup') is True and phase.get('checks') == 280,
            'SQLite phase is incomplete')
    require(phase.get('apk_sha256') == apk_sha and phase.get('installed_apk_sha256') == apk_sha and
            phase.get('build_receipt_sha256') == build_sha, 'SQLite APK producer/installed hashes differ')
    require(sha256_file(path.parent / 'sqlite-build-result.json') == build_sha,
            'Copied build receipt differs from the single producer')
    instrument = path.parent / 'sqlite-instrumentation.log'
    receipt_path = path.parent / 'sqlite-runtime-receipt.json'
    receipt = validate(instrument.read_text(encoding='utf-8'), phase['nonce'],
                       entry['image']['api'], entry['application_page_size_bytes'])
    require(json.loads(receipt_path.read_text(encoding='utf-8')) == receipt,
            'Stored runtime receipt differs from independently validated instrumentation output')
    require(phase.get('runtime_receipt_sha256') == sha256_file(receipt_path) and
            phase.get('instrumentation_log_sha256') == sha256_file(instrument),
            'SQLite runtime evidence hash differs')
    return {'target': target, 'status': 'PASS', 'api': entry['image']['api'], 'minor': entry['image']['minor'],
            'tag': entry['image']['tag'], 'application_page_size_bytes': receipt['application_page_size_bytes'],
            'sqlite_page_size_bytes': receipt['sqlite_page_size_bytes'], 'sqlite_version': receipt['sqlite_version'],
            'checks': receipt['checks'], 'apk_sha256': apk_sha, 'matrix_result_sha256': sha256_file(path),
            'manifest_files_verified': count, 'sdk_full_property': version['sdk_full_property'],
            'sdk_int_full_from_property': version['sdk_int_full_from_property']}


def matrix_status(rows, issues):
    return ('PASS_21_NEUTRAL_SQLITE_TARGETS_ONLY'
            if not issues and set(rows) == set(TARGETS) and
            all(row.get('status') == 'PASS' for row in rows.values()) else 'BLOCKED')


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
    report = {'schema_version': 1, 'status': 'BLOCKED', 'expected_targets': 21, 'rows': {}, 'issues': [],
              'waex_tested': False, 'lsposed_tested': False, 'real_arm64_16k_validated': False,
              'performance_improvement_claimed': False}
    try:
        context_check(os.environ)
        lock, _ = checked_lock(args.lock, 'api24')
        require(args.build_job_result == 'success', 'The single APK producer job did not succeed')
        require(re.fullmatch(r'[0-9a-f]{64}', args.apk_sha256) and
                re.fullmatch(r'[0-9a-f]{64}', args.build_receipt_sha256), 'Producer hashes missing')
        report.update(github_run_id=os.environ.get('GITHUB_RUN_ID'),
                      github_run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                      github_head_sha=os.environ.get('GITHUB_SHA'),
                      apk_sha256=args.apk_sha256, build_receipt_sha256=args.build_receipt_sha256,
                      lock_sha256=sha256_file(args.lock))
        seen = set()
        for path in sorted(args.reports.rglob('matrix-result.json')):
            target = None
            try:
                raw = json.loads(path.read_text(encoding='utf-8'))
                target = raw.get('target')
                require(target in TARGETS and target not in seen, 'Duplicate or unexpected target receipt')
                seen.add(target)
                row = validate_row(path, lock, report['lock_sha256'], report['github_run_id'],
                                   report['github_run_attempt'], report['github_head_sha'],
                                   args.apk_sha256, args.build_receipt_sha256)
                artifact = args.reports / path.relative_to(args.reports).parts[0]
                bootstraps = list(artifact.rglob('bootstrap-result.json'))
                require(len(bootstraps) == 1, 'Exactly one bootstrap receipt per target artifact is required')
                bootstrap = json.loads(bootstraps[0].read_text(encoding='utf-8'))
                verify_manifest(bootstraps[0].parent)
                require(bootstrap.get('status') == 'PASS' and bootstrap.get('license_files_unchanged') is True and
                        bootstrap.get('source_sha256') == lock['source_sha256']['qa/android_emulator_lab_bootstrap.py'],
                        'Fresh runner bootstrap is incomplete')
                report['rows'][target] = row
            except Exception as exc:
                report['issues'].append(str(path.relative_to(args.reports)) + ': ' + type(exc).__name__ + ': ' + str(exc))
                if target in TARGETS:
                    report['rows'][target] = {'target': target, 'status': 'BLOCKED', 'error': str(exc)}
        for target in TARGETS:
            if target not in report['rows']:
                report['rows'][target] = {'target': target, 'status': 'MISSING'}
                report['issues'].append('Missing complete target artifact: ' + target)
    except Exception as exc:
        report['issues'].append(type(exc).__name__ + ': ' + str(exc))
    report['passed_targets'] = sum(row.get('status') == 'PASS' for row in report['rows'].values())
    report['status'] = matrix_status(report['rows'], report['issues'])
    save(args.out, 'matrix-summary.json', report)
    lines = ['# Neutral Android SQLite matrix', '', '**' + report['status'] + '**', '',
             '| Target | Result | App page bytes | SQLite page bytes | Checks |',
             '| --- | --- | ---: | ---: | ---: |']
    for target in sorted(TARGETS):
        row = report['rows'].get(target, {'status': 'MISSING'})
        lines.append('| ' + target + ' | ' + row['status'] + ' | ' +
                     ' | '.join(str(row.get(key, '')) for key in
                                ('application_page_size_bytes', 'sqlite_page_size_bytes', 'checks')) + ' |')
    lines += ['', 'Scope: neutral synthetic SQLite in x86_64 AVDs. Simulated 16 KiB images do not validate real ARM64.',
              'No WAEX, WhatsApp, LSPosed, JNI or performance-improvement claim.', '']
    markdown = '\n'.join(lines)
    (args.out / 'matrix-summary.md').write_text(markdown, encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as stream:
            stream.write(markdown)
    print(json.dumps({'status': report['status'], 'passed_targets': report['passed_targets'],
                      'issues': report['issues']}))
    return 0 if report['status'] == 'PASS_21_NEUTRAL_SQLITE_TARGETS_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
