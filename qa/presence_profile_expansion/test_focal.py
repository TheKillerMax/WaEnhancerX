#!/usr/bin/env python3
"""New host-only identity controls; no real subprocess, compiler, APK or emulator."""
import argparse
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
from presence_profile_expansion import guard, identity, run_lab
from presence_profile_expansion.probe import build_presence_art_probe as builder
from presence_profile_expansion.probe import run_presence_art_probe as launcher
from android_emulator_lab_matrix import TARGETS, expected_minor, checked_lock as matrix_lock

SYNTHETIC_COMMIT = '1234567890abcdef' * 2 + '12345678'
SYNTHETIC_RUN = '123456789'
SYNTHETIC_BOOT = '12345678-1234-1234-1234-123456789abc'
SYNTHETIC_APK = b'SYNTHETIC_NOT_AN_APK_PRESENCE15_CONTROL'
SYNTHETIC_APK_SHA = hashlib.sha256(SYNTHETIC_APK).hexdigest()
SYNTHETIC_PATH = '/data/app/qa/' + identity.PACKAGE + '-synthetic/base.apk'


def check(value, message):
    if not value:
        raise RuntimeError(message)


def synthetic_env(event_path):
    return {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': guard.REPOSITORY,
            'GITHUB_REF': guard.REF, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_HEAD_REF': '', 'GITHUB_SHA': SYNTHETIC_COMMIT, 'GITHUB_RUN_ID': SYNTHETIC_RUN,
            'GITHUB_EVENT_PATH': str(event_path)}


def synthetic_event():
    return {'repository': {'full_name': guard.REPOSITORY, 'private': False},
            'ref': guard.REF, 'after': SYNTHETIC_COMMIT, 'deleted': False}


def synthetic_contract(target='api37.2-16k'):
    api, _, pages = TARGETS[target]
    nonce = '1234567890abcdef' * 2
    return {'target': target, 'api': api, 'minor': expected_minor(target), 'page_bytes': pages,
            'nonce': nonce, 'run_id': 'presence-' + nonce, 'boot_id': SYNTHETIC_BOOT,
            'producer_commit': SYNTHETIC_COMMIT, 'github_run_id': SYNTHETIC_RUN,
            'github_run_attempt': '1', 'apk_sha256': SYNTHETIC_APK_SHA,
            'apk_bytes': len(SYNTHETIC_APK), 'installed_path': SYNTHETIC_PATH}


def synthetic_report(contract):
    header = bytearray(64)
    header[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', header, 16, 3, 62, 1)
    struct.pack_into('<H', header, 52, 64)
    modern = contract['api'] >= 36
    measured = {'schema': identity.SCHEMA, 'status': 'PASS', 'target': contract['target'],
        'api': contract['api'], 'sdk_int_full': contract['api'] * 100000 + contract['minor'] if modern else None,
        'sdk_full_major': contract['api'] if modern else None, 'sdk_full_minor': contract['minor'] if modern else None,
        'sdk_full_method': identity.FULL_METHOD if modern else 'NOT_READ_API_LT_36',
        'minor_policy': 'MEASURED_SDK_INT_FULL' if modern else 'LEGACY_MINOR_ZERO_POLICY_NOT_OBSERVED',
        'process_is_64_bit': True, 'elf_class': 2, 'elf_machine': 62, 'elf_endian': 'little',
        'elf_header_hex': header.hex(), 'elf_header_sha256': hashlib.sha256(header).hexdigest(),
        'executable_path': '/system/bin/app_process64', 'process_uid': 10123, 'process_pid': 1234,
        'application_page_size_bytes': contract['page_bytes'],
        'page_size_method': 'android.system.Os.sysconf(_SC_PAGE_SIZE)',
        'nonce': contract['nonce'], 'run_id': contract['run_id'], 'host_boot_id_binding': contract['boot_id'],
        'boot_binding_method': identity.BOOT_METHOD, 'producer_commit': contract['producer_commit'],
        'producer_run_id': contract['github_run_id'], 'producer_attempt': '1',
        'github_run_id': contract['github_run_id'], 'github_run_attempt': '1',
        'apk_sha256': contract['apk_sha256'], 'apk_bytes': contract['apk_bytes'], 'apk_path': contract['installed_path']}
    return {'schema_version': 1, 'run_id': contract['run_id'], 'api': contract['api'],
            'process_identity': measured, 'application_page_size_bytes': contract['page_bytes'],
            'environment': {'application_page_size_bytes': contract['page_bytes'],
                            'page_size_method': 'android.system.Os.sysconf(_SC_PAGE_SIZE)'},
            'candidate_variant': 'positive', 'tests': 4, 'passed': 4, 'failures': 0, 'errors': 0, 'skipped': 0,
            'cases': [{'name': name, 'status': 'PASS', 'observations': [
                {'phase': phase, 'png': 'synthetic_' + str(index) + '_' + phase + '.png'} for phase in launcher.PHASES[index]]}
                for index, name in enumerate(launcher.CASES)]}


def changed_identity(contract, key, value):
    report = synthetic_report(contract)
    report['process_identity'][key] = value
    return identity.verified_process_identity(report, contract)


class AdbDouble:
    """Only subprocess.run is replaced; every unexpected command raises."""
    def __init__(self, mode):
        self.mode, self.installed, self.instrumented = mode, False, False
        self.commands, self.report = [], None

    def __call__(self, command, **kwargs):
        args = list(command)[3:]
        self.commands.append(args)
        stdout, stderr, code = b'', b'', 0
        if args == ['get-state']:
            stdout = b'device\n'
        elif args == ['shell', 'getprop', 'ro.kernel.qemu']:
            stdout = b'1\n'
        elif args == ['shell', 'getprop', 'ro.build.version.sdk']:
            stdout = b'37\n'
        elif args == ['shell', 'cat', '/proc/sys/kernel/random/boot_id']:
            wrong = self.mode == 'boot_mismatch' or (self.mode == 'boot_drift' and self.instrumented)
            stdout = ((('87654321' + SYNTHETIC_BOOT[8:]) if wrong else SYNTHETIC_BOOT) + '\n').encode()
        elif args == ['shell', 'pm', 'path', identity.PACKAGE]:
            stdout, code = ((('package:' + SYNTHETIC_PATH + '\n').encode(), 0) if self.installed else (b'', 1))
        elif args[:1] == ['install']:
            check(args[:4] == ['install', '-t', '--abi', 'x86_64'] and not self.installed,
                  'Unexpected install/replacement command in double')
            self.installed, stdout = True, b'Success\n'
        elif args[:1] == ['pull']:
            check(args[1] == SYNTHETIC_PATH and self.installed, 'Unexpected pull in double')
            Path(args[2]).write_bytes(SYNTHETIC_APK)
        elif args[:3] == ['shell', 'am', 'instrument']:
            check(args[3:7] == ['--abi', 'x86_64', '-w', '-r'] and self.installed,
                  'Instrumentation did not request actual x86_64')
            fields = {}
            tail = args[7:-1]
            while tail:
                check(tail[0] == '-e' and len(tail) >= 3, 'Unexpected instrumentation arguments')
                fields[tail[1]] = tail[2]
                tail = tail[3:]
            contract = synthetic_contract()
            contract.update(nonce=fields['nonce'], run_id=fields['run_id'])
            check(fields['target'] == contract['target'] and fields['expected_minor'] == '2'
                  and fields['producer_commit'] == SYNTHETIC_COMMIT and fields['github_run_id'] == SYNTHETIC_RUN
                  and fields['host_boot_id'] == SYNTHETIC_BOOT and fields['expected_apk_sha256'] == SYNTHETIC_APK_SHA,
                  'Instrument arguments lost the caller contract')
            self.report = synthetic_report(contract)
            if self.mode == 'identity_mismatch':
                self.report['process_identity']['process_is_64_bit'] = False
            stdout = ('INSTRUMENTATION_RESULT: qa_result=' + json.dumps(self.report) +
                      '\nINSTRUMENTATION_CODE: -1\n').encode()
            self.instrumented = True
        elif args[:4] == ['exec-out', 'run-as', identity.PACKAGE, 'cat']:
            check(self.report is not None, 'Evidence read before instrumentation')
            stdout = json.dumps(self.report).encode() if args[-1].endswith('result.json') else b'\x89PNG\r\n\x1a\nSYNTHETIC_NOT_A_PIXEL_IMAGE'
        elif args == ['uninstall', identity.PACKAGE]:
            check(self.installed, 'Unexpected duplicate uninstall')
            self.installed, stdout = False, b'Success\n'
        else:
            raise RuntimeError('Unexpected command reached the explicit double: ' + repr(args))
        return subprocess.CompletedProcess(command, code, stdout, stderr)


def run_launcher_double(mode, parent):
    folder = parent / mode
    folder.mkdir()
    apk = folder / 'synthetic.apk'
    apk.write_bytes(SYNTHETIC_APK)
    event = folder / 'event.json'
    event.write_text(json.dumps(synthetic_event()))
    out = folder / 'receipt'
    fake = AdbDouble(mode)
    command = ['--adb', str(folder / 'nonexistent-adb'), '--serial', 'emulator-5580',
               '--api', '37', '--page-bytes', '16384', '--apk', str(apk),
               '--expected-sha256', SYNTHETIC_APK_SHA, '--out', str(out), '--target', 'api37.2-16k',
               '--minor', '2', '--expected-boot-id', SYNTHETIC_BOOT,
               '--producer-commit', SYNTHETIC_COMMIT, '--github-run-id', SYNTHETIC_RUN, '--github-run-attempt', '1']
    with patch.dict(os.environ, synthetic_env(event), clear=True), patch.object(launcher.subprocess, 'run', fake), contextlib.redirect_stdout(io.StringIO()):
        try:
            launcher.main(command)
        except SystemExit as error:
            check(error.code == 1 and mode != 'positive', 'Unexpected launcher exit')
    value = json.loads((out / 'receipt.json').read_bytes())
    installs = [x for x in fake.commands if x[:1] == ['install']]
    uninstalls = [x for x in fake.commands if x[:1] == ['uninstall']]
    if mode == 'positive':
        check(value['status'] == 'PASS' and len(installs) == len(uninstalls) == 1
              and not fake.installed, 'New launcher did not preserve success and cleanup')
        built = {'workflow_commit': SYNTHETIC_COMMIT, 'run_id': SYNTHETIC_RUN, 'attempt': '1',
                 'apk': {'bytes': len(SYNTHETIC_APK), 'sha256': SYNTHETIC_APK_SHA}}
        run_lab.validate_receipt(value, 37, SYNTHETIC_APK_SHA, out, 16384, 'api37.2-16k', 2, SYNTHETIC_BOOT, built)
    elif mode == 'boot_mismatch':
        check(value['status'] == 'FAIL' and not installs and not uninstalls,
              'Boot mismatch reached an install/uninstall')
    elif mode == 'identity_mismatch':
        check(value['status'] == 'FAIL' and len(installs) == len(uninstalls) == 1
              and not fake.installed and value['cleanup']['status'] == 'PASS',
              'Identity failure did not preserve owned cleanup')
    elif mode == 'boot_drift':
        check(value['status'] == 'FAIL' and len(installs) == 1 and not uninstalls
              and value['cleanup']['status'] == 'identity_unverified_not_removed',
              'Changed boot allowed a destructive package action')
    return {'mode': mode, 'adb_is_double': True, 'install_count': len(installs),
            'uninstall_count': len(uninstalls), 'status': value['status'],
            'receipt_sha256': hashlib.sha256((out / 'receipt.json').read_bytes()).hexdigest()}


def functions(path):
    return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_text()).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    def case(name, action, rejection=False):
        try:
            detail = action()
        except (RuntimeError, ValueError, TypeError, KeyError) as error:
            if not rejection:
                raise
            rows.append({'name': name, 'status': 'PASS', 'expected': 'REJECT',
                         'observed_exception': type(error).__name__, 'reason': str(error)})
        else:
            check(not rejection, 'Counterexample was accepted: ' + name)
            rows.append({'name': name, 'status': 'PASS', 'expected': 'ACCEPT_OR_EQUIVALENT', 'detail': detail})

    status = 'FAIL'
    error = None
    try:
        case('frozen_source_closure', lambda: {'files': len(guard.checked_sources()['execution_sources'])})
        legacy, modern = synthetic_contract('api27'), synthetic_contract()
        case('synthetic_legacy_27_policy', lambda: identity.verified_process_identity(synthetic_report(legacy), legacy))
        case('synthetic_minor_37_2_simulated_16k', lambda: identity.verified_process_identity(synthetic_report(modern), modern))
        mutations = [
            ('missing_sdk_full', 'sdk_int_full', None), ('nonpositive_sdk_full', 'sdk_int_full', -1),
            ('major_only_is_not_minor', 'sdk_full_minor', 0), ('wrong_reflected_major', 'sdk_full_major', 36),
            ('metadata_is_not_field_measurement', 'sdk_full_method', 'ro.build.version.sdk_full'),
            ('synthetic_full_claim_rejected', 'minor_policy', 'LEGACY_MINOR_ZERO_POLICY_NOT_OBSERVED'),
            ('process_32_rejected', 'process_is_64_bit', False), ('bool_not_int_api', 'api', True),
            ('arm64_machine_rejected', 'elf_machine', 183), ('elf32_rejected', 'elf_class', 1),
            ('big_endian_rejected', 'elf_endian', 'big'), ('wrong_header_hash', 'elf_header_sha256', '0' * 64),
            ('truncated_elf', 'elf_header_hex', '00' * 63), ('wrong_pages', 'application_page_size_bytes', 4096),
            ('stale_nonce', 'nonce', 'f' * 32), ('stale_run_id', 'run_id', 'presence-' + 'f' * 32),
            ('stale_boot_binding', 'host_boot_id_binding', '87654321' + SYNTHETIC_BOOT[8:]),
            ('boot_echo_is_not_app_read', 'boot_binding_method', 'app_kernel_boot_read'),
            ('wrong_producer_commit', 'producer_commit', 'f' * 40),
            ('wrong_embedded_producer_run', 'producer_run_id', '999'),
            ('wrong_workflow_run', 'github_run_id', '999'), ('repeat_attempt', 'github_run_attempt', '2'),
            ('wrong_apk_hash', 'apk_sha256', 'f' * 64), ('wrong_apk_bytes', 'apk_bytes', 1),
            ('foreign_apk_path', 'apk_path', '/data/app/foreign/base.apk'),
            ('root_process_rejected', 'process_uid', 0),
        ]
        for name, key, value in mutations:
            case(name, lambda k=key, v=value: changed_identity(modern, k, v), True)
        case('legacy_must_not_claim_full_read', lambda: changed_identity(legacy, 'sdk_int_full', 2700000), True)
        unknown = synthetic_report(modern)
        unknown['process_identity']['invented_measurement'] = True
        case('unknown_identity_field', lambda: identity.verified_process_identity(unknown, modern), True)
        env, event = synthetic_env('/not/read'), synthetic_event()
        case('new_first_push_context', lambda: guard.verify_context(env, event, 'Linux', 'x86_64'))
        for key, value in [('GITHUB_REF', 'refs/heads/nightly'), ('GITHUB_RUN_ATTEMPT', '2'),
                           ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_REPOSITORY', 'foreign/repository')]:
            bad = dict(env); bad[key] = value
            case('context_reject_' + key, lambda b=bad: guard.verify_context(b, event, 'Linux', 'x86_64'), True)
        wrong = copy.deepcopy(event); wrong['after'] = 'f' * 40
        case('push_after_must_equal_checkout', lambda: guard.verify_context(env, wrong, 'Linux', 'x86_64'), True)

        def target_set():
            check(len(guard.TARGET_NAMES) == 15 and len(set(guard.TARGET_NAMES)) == 15
                  and not set(guard.TARGET_NAMES) & set(guard.QUALIFIED_EXCLUDED), 'Qualified profile leaked')
            check(set(guard.TARGET_NAMES) | set(guard.QUALIFIED_EXCLUDED) == set(TARGETS), 'Matrix21 partition differs')
            for name in guard.TARGET_NAMES:
                lock, entry = matrix_lock(ROOT / 'qa/android_emulator_lab_matrix_lock.json', name)
                api, _, pages = TARGETS[name]
                ctx = SimpleNamespace(target=name, api=api, minor=expected_minor(name),
                    application_page_size_bytes=pages, serial='emulator-5580',
                    guest={'abi': 'x86_64', 'sdk': str(api), 'application_page_size_bytes': str(pages)})
                run_lab.validate_boot_context(ctx, name)
                check(entry['image']['minor'] == expected_minor(name), 'Matrix minor differs')
            workflow = (ROOT / '.github/workflows/android-presence-profile-expansion.yml').read_text()
            matrix = re.findall(r'target: \[([^\]]+)\]', workflow)
            check(len(matrix) == 1 and tuple(x.strip() for x in matrix[0].split(',')) == guard.TARGET_NAMES
                  and 'workflow_dispatch' not in workflow and 'max-parallel: 2' in workflow
                  and 'test_presence_art_host.py' not in workflow, 'Workflow scope differs')
            return {'new_profiles': list(guard.TARGET_NAMES), 'historical_excluded': list(guard.QUALIFIED_EXCLUDED)}
        case('matrix21_partition_and_new_minor_contexts', target_set)

        def inheritance():
            pairs = [('pilot.py', 'android_emulator_lab_pilot.py', {'main'}),
                     ('bootstrap.py', 'android_emulator_lab_bootstrap.py', {'main'}),
                     ('probe/build_presence_art_probe.py', 'presence_art_probe/build_presence_art_probe.py',
                      {'main', 'compiler_contract', 'generate', 'validate_producer'}),
                     ('probe/run_presence_art_probe.py', 'presence_art_probe/run_presence_art_probe.py', {'main'})]
            counts = {}
            for new, old, allowed in pairs:
                a, b = functions(HERE / new), functions(ROOT / 'qa' / old)
                changed = {name for name in set(a) | set(b) if a.get(name) != b.get(name)}
                check(changed <= allowed, 'Unexpected inherited function changed: ' + new + ' ' + str(changed))
                counts[new] = {'identical_functions': len(set(a) & set(b) - changed), 'changed': sorted(changed)}
            old = (ROOT / 'qa/presence_art_probe/PresenceInstrumentation.kt.in').read_text()
            new = (HERE / 'probe/PresenceInstrumentation.kt.in').read_text()
            marker = '    private fun onMain(block: () -> Unit) {'
            check(old[old.index(marker):] == new[new.index(marker):], 'Renderer fixtures/oracles/helpers changed')
            check(new.index('processIdentity = measureProcessIdentity()') < new.index('activity = startActivitySync'),
                  'Identity no longer precedes all Android cases')
            for name in ('AndroidManifest.xml', 'PresenceActivity.java', 'res/values/ids.xml'):
                check((HERE / 'probe' / name).read_bytes() == (ROOT / 'qa/presence_art_probe' / name).read_bytes(),
                      'Manifest/activity/resource drift: ' + name)
            return counts
        case('inherited_functions_and_pixel_suffix_unchanged', inheritance)

        with tempfile.TemporaryDirectory(prefix='waex-presence15-host-') as raw:
            temporary = Path(raw)
            def generated_contract():
                generated = temporary / 'generated'
                generated.mkdir()
                observed = builder.generate(args.source.resolve(), generated, 'positive', None,
                    {'workflow_commit': SYNTHETIC_COMMIT, 'run_id': SYNTHETIC_RUN, 'attempt': '1'})
                historical = json.loads((HERE / 'oracle_contract.json').read_bytes())['contract']
                for key in ('inputs', 'oracles', 'renderer_method_sha256', 'positive_extracted_harness_sha256',
                            'compiled_harness_sha256', 'reference_harness_compared', 'compile_bindings', 'variant', 'scope'):
                    check(observed[key] == historical[key], 'Generated source projection changed: ' + key)
                kotlin = (generated / 'generated/PresenceInstrumentation.kt').read_text()
                check('__PRODUCER_' not in kotlin and SYNTHETIC_COMMIT in kotlin and SYNTHETIC_RUN in kotlin,
                      'Producer tokens were not integrated into new source')
                return {'historical_renderer_sha256': observed['compiled_harness_sha256'],
                        'oracle_count': len(observed['oracles']), 'generated_only': True,
                        'compiler_executed': False, 'pixel_tests_executed': False}
            case('generate_only_matches_frozen_E_oracles', generated_contract)
            for mode in ('positive', 'boot_mismatch', 'identity_mismatch', 'boot_drift'):
                case('launcher_double_' + mode, lambda m=mode: run_launcher_double(m, temporary))
            def source_drift():
                changed = temporary / 'modified-source-root'
                for relative in guard.checked_sources()['execution_sources']:
                    path = changed / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, path)
                path = changed / 'qa/presence_profile_expansion/lock.json'
                shutil.copyfile(HERE / 'lock.json', path)
                (changed / 'qa/presence_profile_expansion/identity.py').write_text('# deliberately wrong controlled copy\n')
                return guard.checked_sources(changed)
            case('source_hash_drift_before_external_effect', source_drift, True)
        status = 'PASS'
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        result = {'schema': 'WAEX_PRESENCE15_FOCAL_HOST_CONTROLS_V1', 'status': status,
                  'python_optimized': not __debug__, 'controls': len(rows), 'results': rows, 'failure': error,
                  'scope': 'Synthetic host records, explicit ADB subprocess double, static inheritance and source generation only',
                  'android_executed': False, 'compiler_executed': False, 'github_mutated': False,
                  'prior_qualified_suites_repeated': 0,
                  'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}}
        (args.out / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': status, 'controls': len(rows), 'result': str(args.out / 'result.json')}))


if __name__ == '__main__':
    main()

