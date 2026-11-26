#!/usr/bin/env python3
"""Check new Runtime input boundaries with real locked bytes and no network.

These are CLI/POM/receipt controls. Gradle selection and the Test classpath still
require the separate native framework execution; these controls do not simulate it.
"""
import argparse
import contextlib
import copy
import io
import itertools
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import framework_dependency_bundle as bundles
import runtime_framework_inputs as inputs
import verify_runtime_framework as runner

OUT = None
BUNDLE = None
ORIGIN = None


class RuntimeInputChecks(unittest.TestCase):
    def setUp(self):
        self.out = OUT / self._testMethodName
        self.out.mkdir()

    def prepare(self):
        return inputs.prepare(BUNDLE, self.out, ORIGIN['run_id'], ORIGIN['run_attempt'], ORIGIN['head_sha'])

    def receipt(self, record):
        source = self.out / 'native-repository/org/robolectric/nativeruntime-dist-compat/1.0.19' / (inputs.NATIVE + '.jar')
        used = self.out / 'actual-test-input.jar'
        os.link(source, used)
        native = record['native']
        return {'coordinate': 'org.robolectric:nativeruntime-dist-compat:1.0.19',
                'path': str(used), 'bytes': native['bytes'], 'sha256': native['sha256'],
                'resolved_artifact_path': str(source), 'resolved_artifact_bytes': native['bytes'],
                'resolved_artifact_sha256': native['sha256'], 'on_test_classpath': True,
                'matched_test_classpath_files': 1, 'sdk_directory': record['sdk_directory'], 'sdk_offline': True}

    def save_receipt(self, record):
        (self.out / 'gradle-native-resolution.json').write_text(json.dumps(record) + '\n')

    def test_incomplete_cli_origin_stops_before_preparation_or_public_apk(self):
        switches = ('--bundle-run-id', '--bundle-run-attempt', '--bundle-head-sha')
        values = ('9000000000000000001', '1', '0' * 40)
        for bits in itertools.product((False, True), repeat=4):
            has_bundle, *present = bits
            if (not has_bundle and not any(present)) or (has_bundle and all(present)):
                continue
            target = self.out / ('case-' + ''.join(map(lambda value: str(int(value)), bits)))
            args = [str(Path(runner.__file__)), '--out', str(target)]
            if has_bundle:
                args += ['--framework-bundle', str(BUNDLE)]
            for selected, name, value in zip(present, switches, values):
                if selected:
                    args += [name, value]
            stderr = io.StringIO()
            with self.subTest(bits=bits), patch.object(sys, 'argv', args), contextlib.redirect_stderr(stderr), patch.object(inputs, 'prepare', side_effect=AssertionError('Preparation must not begin')) as prepare, patch.object(runner.urllib.request, 'urlopen', side_effect=AssertionError('Public APK network forbidden')) as fetch:
                with self.assertRaises(SystemExit) as failure:
                    runner.main()
                self.assertEqual(2, failure.exception.code)
                self.assertIn('requires explicit --bundle-run-id', stderr.getvalue())
                self.assertFalse(target.exists())
                prepare.assert_not_called()
                fetch.assert_not_called()

    def test_complete_but_invalid_origin_cannot_reach_public_apk(self):
        for name, values in (('run', ('0', '1', '0' * 40)), ('attempt', ('1', '0', '0' * 40)), ('head', ('1', '1', 'main'))):
            target = self.out / name
            args = [str(Path(runner.__file__)), '--out', str(target), '--framework-bundle', str(BUNDLE),
                    '--bundle-run-id', values[0], '--bundle-run-attempt', values[1], '--bundle-head-sha', values[2]]
            with self.subTest(name=name), patch.object(sys, 'argv', args), patch.object(runner.urllib.request, 'urlopen', side_effect=AssertionError('Public APK network forbidden')) as fetch:
                with self.assertRaises(ValueError):
                    runner.main()
                fetch.assert_not_called()
                self.assertFalse((target / 'native-repository').exists())
                self.assertFalse(list((target / 'apks').glob('*.apk')))

    def test_original_pom_is_copied_without_replacing_its_metadata(self):
        record = self.prepare()
        module = self.out / 'native-repository/org/robolectric/nativeruntime-dist-compat/1.0.19'
        self.assertEqual({inputs.POM.name, inputs.NATIVE + '.jar'}, {path.name for path in module.iterdir()})
        self.assertEqual(inputs.POM.read_bytes(), (module / inputs.POM.name).read_bytes())
        self.assertEqual(inputs.POM_PIN['sha256'], record['pom']['sha256'])
        self.assertEqual(39, record['bundle']['verified_files'])

    def test_changed_pom_is_rejected_before_a_repository_is_created(self):
        altered = self.out / 'changed.pom'
        # Same XML metadata and coordinates: the original raw bytes still matter.
        altered.write_bytes(inputs.POM.read_bytes() + b'\n')
        with patch.object(inputs, 'POM', altered):
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                self.prepare()
        self.assertFalse((self.out / 'native-repository').exists())

    def test_verified_test_copy_may_have_a_different_path(self):
        record = self.prepare()
        receipt = self.receipt(record)
        self.assertNotEqual(receipt['path'], receipt['resolved_artifact_path'])
        self.save_receipt(receipt)
        inputs.finish(record, self.out)
        self.assertTrue(record['accepted'])
        self.assertTrue(record['after_execution_bundle']['accepted'])

    def test_changed_actual_test_bytes_cannot_hide_behind_a_valid_receipt(self):
        record = self.prepare()
        receipt = self.receipt(record)
        different = self.out / 'changed-test-input.jar'
        different.write_bytes(b'changed bytes in an owned disposable file')
        receipt['path'] = str(different)
        self.save_receipt(receipt)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            inputs.finish(record, self.out)
        self.assertFalse((self.out / 'framework-inputs.json').exists())

    def test_unbound_classpath_or_online_sdk_cannot_be_accepted(self):
        record = self.prepare()
        receipt = self.receipt(record)
        for changed in ({'on_test_classpath': False}, {'matched_test_classpath_files': 0},
                        {'matched_test_classpath_files': True}, {'resolved_artifact_sha256': '0' * 64}, {'sdk_offline': False}):
            with self.subTest(changed=changed):
                self.save_receipt(dict(receipt, **changed))
                with self.assertRaises(ValueError):
                    inputs.finish(copy.deepcopy(record), self.out)
                self.assertFalse((self.out / 'framework-inputs.json').exists())


def main():
    global OUT, BUNDLE, ORIGIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    OUT, BUNDLE = args.out.resolve(), args.bundle.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    ORIGIN = json.loads((BUNDLE / 'bundle.json').read_bytes())['origin']
    before = bundles.verify(BUNDLE, inputs.QA / 'framework_dependency_lock.json', ORIGIN)
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeInputChecks)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    after = bundles.verify(BUNDLE, inputs.QA / 'framework_dependency_lock.json', ORIGIN)
    report = {'accepted': result.wasSuccessful(), 'tests': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'bundle_before': before, 'bundle_after': after,
              'source_sha256': {Path(path).name: bundles.sha(Path(path)) for path in (inputs.__file__, runner.__file__, __file__, inputs.POM)},
              'scope': 'CLI rejection before public APK access, original POM identity, and disposable receipt controls. Actual Gradle/Test selection is verified separately by the native framework run.'}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
