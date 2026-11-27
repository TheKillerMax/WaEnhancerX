#!/usr/bin/env python3
"""Check the split artifact layout against the unchanged complete-bundle verifier.

ZIP fixtures model upload-artifact v4's documented search-root layout and
single-name download destinations. They do not simulate GitHub's service,
replace real JARs or certify an actual hosted artifact transfer.
"""
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

import framework_dependency_bundle as bundle


class SplitTransportChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.deps = self.root / 'producer-deps'
        self.repo = self.root / 'producer-repo'
        self.deps.mkdir()
        self.repo.mkdir()
        self.complete = self.root / 'verified'
        self.target = self.root / 'downloaded'
        self.lock = self.root / 'fixture-lock.json'
        self.origin = bundle.identity('45570182765', '1', 'a' * 40)
        lock = json.loads(bundle.LOCK.read_text(encoding='utf-8'))
        for index, item in enumerate(lock['files']):
            payload = ('DISPOSABLE SPLIT TRANSPORT FIXTURE ' + str(index)).encode()
            item['bytes'] = len(payload)
            item['sha256'] = hashlib.sha256(payload).hexdigest()
            path = self.deps / item['name'] if item['directory'] == 'deps' else self.repo / item['maven_path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.lock.write_text(json.dumps(lock), encoding='utf-8')
        self.network = patch.object(socket, 'socket', side_effect=AssertionError('Offline transport only'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.assertEqual(39, bundle.create(self.complete, self.deps, self.repo, self.lock,
                                           self.origin)['verified_files'])
        self.dep_zip = self.root / 'deps.zip'
        self.sdk_zip = self.root / 'sdks.zip'
        # Multiple upload paths: their common ancestor is the verified bundle.
        with ZipFile(self.dep_zip, 'w', compression=ZIP_STORED) as archive:
            archive.write(self.complete / 'bundle.json', 'bundle.json')
            for path in sorted((self.complete / 'deps').glob('*.jar')):
                archive.write(path, path.relative_to(self.complete).as_posix())
        # A single SDK directory is the second artifact's search root.
        with ZipFile(self.sdk_zip, 'w', compression=ZIP_STORED) as archive:
            for path in sorted((self.complete / 'sdk-jars').glob('*.jar')):
                archive.write(path, path.name)

    def download(self, deps=True, sdks=True):
        # Only locally constructed, disposable test archives are extracted.
        if deps:
            with ZipFile(self.dep_zip) as archive:
                archive.extractall(self.target)
        if sdks:
            with ZipFile(self.sdk_zip) as archive:
                archive.extractall(self.target / 'sdk-jars')

    def verify(self, origin=None):
        return bundle.verify(self.target, self.lock, self.origin if origin is None else origin)

    def test_both_parts_reconstruct_identical_graph(self):
        self.download()
        self.assertEqual(39, self.verify()['verified_files'])
        self.assertEqual(bundle.sha(self.complete / 'bundle.json'), bundle.sha(self.target / 'bundle.json'))
        self.assertTrue((self.target / 'deps/nativeruntime-dist-compat-1.0.19.jar').is_file())
        self.assertEqual({p.relative_to(self.complete).as_posix() for p in self.complete.rglob('*') if p.is_file()},
                         {p.relative_to(self.target).as_posix() for p in self.target.rglob('*') if p.is_file()})

    def test_missing_sdk_part_fails(self):
        self.download(sdks=False)
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_missing_dependency_part_fails(self):
        self.download(deps=False)
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_missing_manifest_fails(self):
        self.download()
        (self.target / 'bundle.json').unlink()
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_tampered_sdk_fails(self):
        self.download()
        path = next((self.target / 'sdk-jars').glob('*.jar'))
        payload = path.read_bytes()
        path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.verify()

    def test_native_runtime_missing_fails(self):
        self.download()
        (self.target / 'deps/nativeruntime-dist-compat-1.0.19.jar').unlink()
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_stale_attempt_run_or_head_fails(self):
        self.download()
        for field, value in [('run_id', '45570182766'), ('run_attempt', '2'), ('head_sha', 'b' * 40)]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'CI origin mismatch'):
                self.verify(dict(self.origin, **{field: value}))

    def test_unreviewed_extra_file_fails(self):
        self.download()
        (self.target / 'sdk-jars/unknown.jar').write_bytes(b'not locked')
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_wrong_download_root_fails(self):
        self.download(sdks=False)
        with ZipFile(self.sdk_zip) as archive:
            archive.extractall(self.target)
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.verify()

    def test_relabelled_manifest_cannot_redefine_bytes(self):
        self.download()
        manifest_path = self.target / 'bundle.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        entry = next(name for name in manifest['files'] if name.startswith('sdk-jars/'))
        (self.target / entry).write_bytes(b'replacement')
        manifest['files'][entry] = {'bytes': 11, 'sha256': hashlib.sha256(b'replacement').hexdigest()}
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.verify()

    def test_production_parts_fit_transfer_budget(self):
        items = bundle.load_lock(bundle.LOCK)
        # Reserve a generous 8 MiB for manifest, archive headers and transport overhead.
        # This bounds the locked input sizes, not GitHub's actual returned ZIP size.
        max_payload = 512 * 1024 * 1024 - 8 * 1024 * 1024
        for directory in ('deps', 'sdk-jars'):
            size = sum(item['bytes'] for item in items if item['directory'] == directory)
            with self.subTest(directory=directory, bytes=size):
                self.assertLessEqual(size, max_payload)


if __name__ == '__main__':
    unittest.main(verbosity=2)
