#!/usr/bin/env python3
"""Host controls for matrix identity, coverage and mocked APK lifecycle.

No Android process is started. Synthetic receipts are not runtime evidence.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import android_emulator_lab_matrix as matrix
from android_emulator_lab_pilot import BootContext, guest_version_identity
from android_emulator_lab_preflight import sha256_file
from summarize_android_emulator_lab_matrix import matrix_status, verify_manifest
from test_android_sqlite_probe import fixture, transcript


class MatrixControls(unittest.TestCase):
    def test_full_sdk_property_matches_aosp_text_and_metadata(self):
        for raw, api, minor, encoded in [('36', 36, 0, 3600000), ('36.0', 36, 0, 3600000),
                                         ('36.1', 36, 1, 3600001), ('37.1', 37, 1, 3700001),
                                         ('37.2', 37, 2, 3700002)]:
            with self.subTest(raw=raw):
                result = guest_version_identity({'sdk': str(api), 'sdk_full_property': raw},
                                                {'api': api, 'minor': minor})
                self.assertEqual(result['sdk_int_full_from_property'], encoded)
                self.assertTrue(result['minor_verified'])
                self.assertFalse(result['java_sdk_int_full_field_read'])
        for raw in ('', '3700002', '37', '37.0', '37.1', '37.-2', '37.100000', '21474.2', '37.2\n', '36.2'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                guest_version_identity({'sdk': '37', 'sdk_full_property': raw}, {'api': 37, 'minor': 2})
        with self.assertRaises(RuntimeError):
            guest_version_identity({'sdk': '36', 'sdk_full_property': '37.2'}, {'api': 37, 'minor': 2})

    def test_legacy_api_does_not_invent_a_minor_version_measurement(self):
        result = guest_version_identity({'sdk': '24', 'sdk_full_property': ''}, {'api': 24, 'minor': 0})
        self.assertIsNone(result['sdk_int_full_from_property'])
        self.assertFalse(result['minor_verified'])
        with self.assertRaises(RuntimeError):
            guest_version_identity({'sdk': '24'}, {'api': 24, 'minor': 1})

    def test_catalog_and_coverage_require_every_target(self):
        self.assertEqual(len(matrix.TARGETS), 21)
        self.assertEqual(sum(x[2] == 16384 for x in matrix.TARGETS.values()), 6)
        self.assertEqual({x[0] for x in matrix.TARGETS.values() if ';default;' in x[1]}, {27, 31, 32})
        rows = {name: {'status': 'PASS'} for name in matrix.TARGETS}
        self.assertEqual(matrix_status(rows, []), 'PASS_21_NEUTRAL_SQLITE_TARGETS_ONLY')
        missing = copy.deepcopy(rows); missing.pop('api37.2-16k')
        self.assertEqual(matrix_status(missing, []), 'BLOCKED')
        replacement = copy.deepcopy(missing); replacement['api99'] = {'status': 'PASS'}
        self.assertEqual(matrix_status(replacement, []), 'BLOCKED')
        blocked = copy.deepcopy(rows); blocked['api24']['status'] = 'BLOCKED'
        self.assertEqual(matrix_status(blocked, []), 'BLOCKED')
        self.assertEqual(matrix_status(rows, ['duplicate artifact']), 'BLOCKED')

    def test_recursive_manifest_preserves_nested_evidence_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'nested').mkdir()
            (root / 'result.json').write_bytes(b'{}')
            (root / 'nested/capture.png').write_bytes(b'synthetic PNG bytes')
            manifest = {p.relative_to(root).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                        for p in root.rglob('*') if p.is_file()}
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(verify_manifest(root), 2)
            (root / 'nested/capture.png').write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                verify_manifest(root)
            (root / 'manifest.json').write_text(json.dumps({'../escape': {'bytes': 0, 'sha256': '0' * 64}}), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                verify_manifest(root)

    def test_producer_contract_uses_actual_builder_field_names_and_pins(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            apk = bundle / 'sqlite-probe.apk'; apk.write_bytes(b'synthetic APK, not installable')
            apk_sha = sha256_file(apk)
            pins = {'qa/build_android_sqlite_probe.py': 'a' * 64,
                    'qa/android_sqlite_probe/AndroidManifest.xml': 'b' * 64,
                    'qa/android_sqlite_probe/SqliteProbeInstrumentation.java': 'c' * 64}
            lock = {'source_sha256': pins, 'tool_sha256': {'java': 'd' * 64},
                    'build_sdk_metadata_sha256': {'metadata': 'e' * 64}}
            receipt = {
                'schema': 'WAEX_SQLITE_PROBE_BUILD_V1', 'status': 'PASS_BUILD_ONLY',
                'package': matrix.PACKAGE, 'instrumentation_component': matrix.COMPONENT,
                'min_sdk': 24, 'target_sdk': 36, 'build_tools_revision': '36.0.0',
                'permissions': [], 'native_libraries': [], 'ephemeral_key_absent': True,
                'runtime_tested': False, 'phone_or_emulator_accessed': False,
                'sdk_installed_or_license_accepted': False,
                'apk': {'file': apk.name, 'bytes': apk.stat().st_size, 'sha256': apk_sha},
                'builder_sha256': pins['qa/build_android_sqlite_probe.py'],
                'source_sha256': {'AndroidManifest.xml': 'b' * 64, 'SqliteProbeInstrumentation.java': 'c' * 64},
                'sdk_metadata': {'metadata': 'e' * 64}, 'tools': {'java': {'sha256': 'd' * 64}},
            }
            path = bundle / 'build-result.json'
            def check(value):
                path.write_text(json.dumps(value), encoding='utf-8')
                return matrix.verified_probe(bundle, apk_sha, sha256_file(path), lock)
            self.assertEqual(check(receipt)[0], apk)
            mutations = [lambda r: r.update(instrumentation_component='wrong'),
                         lambda r: r.update(ephemeral_key_absent=False),
                         lambda r: r.update(min_sdk=True),
                         lambda r: r.update(runtime_tested=True),
                         lambda r: r['source_sha256'].update({'AndroidManifest.xml': 'f' * 64}),
                         lambda r: r['sdk_metadata'].update(metadata='f' * 64),
                         lambda r: r['tools']['java'].update(sha256='f' * 64),
                         lambda r: r['apk'].update(bytes=1)]
            for mutate in mutations:
                value = copy.deepcopy(receipt); mutate(value)
                with self.assertRaises(RuntimeError):
                    check(value)
            path.write_text(json.dumps(receipt), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                matrix.verified_probe(bundle, 'f' * 64, sha256_file(path), lock)

    def lifecycle(self, mode='success', api=24, pages=4096):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp); out = work / 'reports'; out.mkdir()
            apk = work / 'sqlite-probe.apk'; apk.write_bytes(b'synthetic APK bytes')
            build = work / 'build-result.json'; build.write_text('{}', encoding='utf-8')
            apk_sha, build_sha = sha256_file(apk), sha256_file(build)
            result, calls = {}, []
            installed = mode == 'preexisting'
            nonce = '0123456789abcdef0123456789abcdef'
            context = BootContext('api' + str(api), api, 0, pages, Path('/sdk/adb'), 'emulator-5580',
                                  {}, work, out, {'abi': 'x86_64'}, {}, result)

            def invoke(output, name, command, env, **kwargs):
                nonlocal installed
                calls.append((name, command))
                self.assertEqual(command[1:3], ['-s', 'emulator-5580'])
                value = ''
                if name.startswith('sqlite-package-'):
                    value = 'package:' + matrix.PACKAGE + '\n' if installed else ''
                elif name == 'sqlite-install':
                    installed = True
                    if mode == 'ambiguous-install':
                        raise RuntimeError('simulated transport loss after installing')
                    value = 'Success\n'
                elif name.endswith('-path'):
                    value = 'package:/data/app/org.lab.waex.qa.sqlite-test/base.apk\n'
                elif name.endswith('-pull'):
                    Path(command[-1]).write_bytes(b'different APK' if mode == 'wrong-installed-hash' else apk.read_bytes())
                elif name == 'sqlite-instrumentation':
                    receipt = fixture()
                    receipt.update(sdk=api, application_page_size_bytes=pages, run_nonce=nonce)
                    if mode == 'wrong-nonce':
                        receipt['run_nonce'] = 'f' * 32
                    value = transcript(receipt)
                elif name == 'sqlite-uninstall':
                    if mode == 'uninstall-failure':
                        raise RuntimeError('simulated uninstall failure')
                    installed = False; value = 'Success\n'
                else:
                    raise AssertionError(name)
                (out / (name + '.log')).write_text(value, encoding='utf-8')
                return {'returncode': 0, 'failure': None}, value

            with patch.object(matrix, 'verified_probe', return_value=(apk, build, {})), \
                    patch.object(matrix, 'invoke', invoke), patch.object(matrix.secrets, 'token_hex', return_value=nonce):
                action = matrix.sqlite_action(work, apk_sha, build_sha, {})
                if mode == 'success':
                    phase = action(context)
                    self.assertEqual(phase['status'], 'PASS')
                    self.assertEqual(phase['checks'], 280)
                    self.assertEqual(phase['application_page_size_bytes'], pages)
                    self.assertEqual(phase['sqlite_page_size_bytes'], 4096)
                    self.assertTrue(phase['package_absent_after_cleanup'])
                    self.assertFalse(installed)
                else:
                    with self.assertRaises((RuntimeError, ValueError)):
                        action(context)
            phase = json.loads((out / 'sqlite-phase.json').read_text(encoding='utf-8'))
            return phase, [name for name, _ in calls], result, installed

    def test_lifecycle_rechecks_installed_identity_and_separates_page_sizes(self):
        for api, pages in ((24, 4096), (35, 16384)):
            with self.subTest(api=api):
                phase, calls, result, _ = self.lifecycle(api=api, pages=pages)
                self.assertTrue(result['apk_install_attempted'])
                self.assertTrue(result['apk_installed'])
                self.assertEqual(calls.count('sqlite-uninstall'), 1)
                self.assertEqual(calls.count('sqlite-installed-pull'), 1)
                self.assertEqual(calls.count('sqlite-before-uninstall-pull'), 1)
                self.assertTrue(phase['package_absent_after_cleanup'])

    def test_lifecycle_fails_closed_for_identity_nonce_install_and_cleanup_errors(self):
        for mode in ('preexisting', 'wrong-installed-hash', 'wrong-nonce', 'ambiguous-install', 'uninstall-failure'):
            with self.subTest(mode=mode):
                phase, calls, _, installed = self.lifecycle(mode)
                self.assertEqual(phase['status'], 'BLOCKED')
                if mode in ('preexisting', 'wrong-installed-hash'):
                    self.assertNotIn('sqlite-uninstall', calls)
                    self.assertNotIn('sqlite-instrumentation', calls)
                    self.assertTrue(installed)
                if mode == 'preexisting':
                    self.assertNotIn('sqlite-install', calls)
                if mode in ('wrong-nonce', 'ambiguous-install'):
                    self.assertFalse(installed)
                    self.assertTrue(phase['package_absent_after_cleanup'])
                if mode == 'uninstall-failure':
                    self.assertTrue(installed)
                    self.assertFalse(phase['package_absent_after_cleanup'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
