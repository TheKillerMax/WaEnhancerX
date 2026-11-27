#!/usr/bin/env python3
"""Exercise dependency-transfer rejection paths using disposable fixture bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

import framework_dependency_bundle as bundle

OUT = None


class DependencyBundleChecks(unittest.TestCase):
    def setUp(self):
        self.root = OUT / self._testMethodName
        self.root.mkdir()
        self.deps, self.repo = self.root / 'deps', self.root / 'repository'
        self.deps.mkdir()
        self.repo.mkdir()
        self.target = self.root / 'bundle'
        self.lock = self.root / 'fixture-lock.json'
        self.origin = bundle.identity('45570182765', '1', 'a' * 40)
        lock = json.loads(bundle.LOCK.read_text())
        for index, item in enumerate(lock['files']):
            payload = ('DISPOSABLE TEST FIXTURE ' + str(index)).encode()
            item['bytes'], item['sha256'] = len(payload), hashlib.sha256(payload).hexdigest()
            path = self.deps / item['name'] if item['directory'] == 'deps' else self.repo / item['maven_path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.lock.write_text(json.dumps(lock))

    def create(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden in bundle transport')):
            return bundle.create(self.target, self.deps, self.repo, self.lock, self.origin)

    def verify(self, origin=None):
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden in bundle transport')):
            return bundle.verify(self.target, self.lock, origin or self.origin)

    def test_complete_bundle_roundtrip_is_offline_and_keeps_native_runtime(self):
        self.assertEqual(39, self.create()['verified_files'])
        self.assertTrue(self.verify()['accepted'])
        self.assertTrue((self.target / 'deps/nativeruntime-dist-compat-1.0.19.jar').is_file())

    def test_corrupted_bytes_fail_even_at_same_length(self):
        self.create()
        path = next((self.target / 'deps').glob('*.jar'))
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.verify()

    def test_missing_native_runtime_is_rejected(self):
        self.create()
        (self.target / 'deps/nativeruntime-dist-compat-1.0.19.jar').unlink()
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_missing_sdk_is_rejected(self):
        self.create()
        next((self.target / 'sdk-jars').glob('*.jar')).unlink()
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_unreviewed_jar_is_rejected(self):
        self.create()
        (self.target / 'deps/unreviewed.jar').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_unreviewed_directory_is_rejected(self):
        self.create()
        (self.target / 'unexpected').mkdir()
        with self.assertRaisesRegex(ValueError, 'Unexpected bundle directory'):
            self.verify()

    def test_symlink_cannot_substitute_even_identical_bytes(self):
        self.create()
        source = next(self.deps.glob('*.jar'))
        destination = self.target / 'deps' / source.name
        destination.unlink()
        destination.symlink_to(source.resolve())
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.verify()

    def test_wrong_run_is_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'CI origin mismatch'):
            self.verify(dict(self.origin, run_id='45570182766'))

    def test_wrong_attempt_is_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'CI origin mismatch'):
            self.verify(dict(self.origin, run_attempt='2'))

    def test_wrong_source_commit_is_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'CI origin mismatch'):
            self.verify(dict(self.origin, head_sha='b' * 40))

    def test_manifest_cannot_redefine_pinned_bytes(self):
        self.create()
        path = self.target / 'bundle.json'
        manifest = json.loads(path.read_text())
        next(iter(manifest['files'].values()))['sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.verify()

    def test_lock_identity_change_is_rejected(self):
        self.create()
        self.lock.write_text(self.lock.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.verify()

    def test_changed_producer_jar_fails_before_bundle_creation(self):
        next(self.deps.glob('*.jar')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.create()
        self.assertFalse(self.target.exists())

    def test_extra_producer_jar_fails_before_bundle_creation(self):
        (self.deps / 'extra.jar').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'Producer dependency'):
            self.create()
        self.assertFalse(self.target.exists())

    def test_existing_bundle_is_never_overwritten(self):
        self.create()
        before = (self.target / 'bundle.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.create()
        self.assertEqual(before, (self.target / 'bundle.json').read_bytes())

    def test_duplicate_lock_entry_is_rejected(self):
        lock = json.loads(self.lock.read_text())
        lock['files'][1] = dict(lock['files'][0])
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.create()

    def test_unsafe_sdk_path_is_rejected(self):
        lock = json.loads(self.lock.read_text())
        next(i for i in lock['files'] if i['directory'] == 'sdk-jars')['maven_path'] = '../escape.jar'
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'Unsafe SDK'):
            self.create()

    def test_unsafe_dependency_name_is_rejected(self):
        lock = json.loads(self.lock.read_text())
        lock['files'][0]['name'] = '../escape.jar'
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'Unsafe dependency'):
            self.create()

    def test_truncated_lock_is_rejected(self):
        lock = json.loads(self.lock.read_text())
        lock['files'].pop()
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'complete framework'):
            self.create()

    def test_non_ci_identity_is_rejected(self):
        for run, attempt, head in [('0', '1', 'a' * 40), ('1', '', 'a' * 40), ('1', '1', 'main')]:
            with self.subTest(run=run, attempt=attempt, head=head), self.assertRaises(ValueError):
                bundle.identity(run, attempt, head)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(DependencyBundleChecks)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    report = {'accepted': result.wasSuccessful(), 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'scope': 'Disposable transport fixtures only; not Android behavior or a CI artifact download',
              'production_lock_sha256': bundle.sha(bundle.LOCK),
              'helper_sha256': bundle.sha(Path(bundle.__file__))}
    report_path = args.report or OUT / 'result.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
