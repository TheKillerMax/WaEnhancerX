"""Negative controls for compiler identity and the observed D8 diagnostics failure."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build
import toolchain


class ToolchainTests(unittest.TestCase):
    def test_locked_kotlin_runtime_versions_and_dependency_closure(self):
        lock = toolchain.checked_lock()
        self.assertEqual(lock['kotlin_version'], '2.0.20')
        self.assertEqual(lock['java_major'], 21)
        rows = {row['file']: row for row in lock['artifacts']}
        for name in ('kotlin-compiler', 'kotlin-stdlib', 'kotlin-stdlib-jdk7',
                     'kotlin-stdlib-jdk8', 'kotlin-script-runtime'):
            self.assertIn('/2.0.20/' + name + '-2.0.20.jar', rows[name + '.jar']['url'])
        self.assertEqual(len(rows), 9)

    def test_changed_truncated_extended_payloads_are_rejected(self):
        good = b'PK\x00\xff\r\n'
        row = {'file': 'sample.jar', 'bytes': len(good),
               'sha256': hashlib.sha256(good).hexdigest()}
        self.assertEqual(toolchain.checked_payload(good, row), good)
        for bad in (b'X' + good[1:], good[:-1], good + b'\x00'):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                toolchain.checked_payload(bad, row)

    def test_missing_cache_does_not_download(self):
        row = {'url': 'https://repo.maven.apache.org/maven2/test/absent.jar'}
        with tempfile.TemporaryDirectory() as folder, patch.object(toolchain.urllib.request, 'urlopen') as fetch:
            with self.assertRaises(RuntimeError):
                toolchain.payload(row, Path(folder))
            fetch.assert_not_called()

    def test_missing_changed_and_extra_classpath_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); (home / 'lib').mkdir(); (home / 'bin').mkdir()
            jar = home / 'lib/sample.jar'; jar.write_bytes(b'exact bytes')
            launcher = home / 'bin/kotlinc'; launcher.write_text('launcher')
            lock = {'artifacts': [{'file': 'sample.jar', 'bytes': jar.stat().st_size,
                                   'sha256': toolchain.digest(jar)}]}
            pin = toolchain.digest(launcher)
            toolchain.verify_home(home, lock, pin)
            extra = home / 'lib/compose-compiler.jar'; extra.write_bytes(b'extra')
            with self.assertRaises(RuntimeError):
                toolchain.verify_home(home, lock, pin)
            extra.unlink(); jar.write_bytes(b'Exact bytes')
            with self.assertRaises(RuntimeError):
                toolchain.verify_home(home, lock, pin)
            jar.unlink()
            with self.assertRaises(RuntimeError):
                toolchain.verify_home(home, lock, pin)

    def test_changed_launcher_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); (home / 'bin').mkdir()
            launcher = home / 'bin/kotlinc'; launcher.write_text('first')
            pin = toolchain.digest(launcher); launcher.write_text('other')
            with self.assertRaises(RuntimeError):
                toolchain.verify_home(home, {'artifacts': []}, pin)

    def test_symlink_classpath_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); (home / 'bin').mkdir(); (home / 'lib').mkdir()
            launcher = home / 'bin/kotlinc'; launcher.write_text('launcher')
            (home / 'lib/linked.jar').symlink_to(launcher)
            with self.assertRaises(RuntimeError):
                toolchain.verify_home(home, {'artifacts': []}, toolchain.digest(launcher))

    def test_d8_requires_empty_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            for stream in ('stdout', 'stderr'):
                (out / ('candidate-d8.' + stream + '.log')).write_bytes(b'')
            build.require_quiet_d8(out, 'candidate')
            for stream, diagnostic in (
                ('stdout', b'Info: malformed kotlin.Metadata: version 2.4.0 exceeds 2.2.0'),
                ('stderr', b'Warning: An error occurred when parsing kotlin metadata.'),
                ('stdout', b'an unrelated new diagnostic'),
                ('stderr', b'\n'),
            ):
                with self.subTest(stream=stream, diagnostic=diagnostic):
                    path = out / ('candidate-d8.' + stream + '.log')
                    path.write_bytes(diagnostic)
                    with self.assertRaises(RuntimeError):
                        build.require_quiet_d8(out, 'candidate')
                    self.assertEqual(path.read_bytes(), diagnostic)
                    path.write_bytes(b'')

    def test_zip_envelope_is_reproducible_and_preserves_class_bytes(self):
        payload = b'dex\n037\x00\x00\xff\r\n'
        archives = []
        for _ in range(2):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
                build.zip_member(archive, 'classes.dex', payload)
            archives.append(buffer.getvalue())
        self.assertEqual(archives[0], archives[1])
        with zipfile.ZipFile(io.BytesIO(archives[0])) as archive:
            self.assertEqual(archive.read('classes.dex'), payload)
            self.assertEqual(archive.getinfo('classes.dex').date_time, (1980, 1, 1, 0, 0, 0))

    def test_artifact_pin_changed_on_same_version_is_rejected(self):
        lock = toolchain.checked_lock()
        row = lock['artifacts'][0]
        self.assertNotEqual(row['sha256'], '0' * 64)
        with self.assertRaises(RuntimeError):
            toolchain.checked_payload(b'not the released compiler', row)


if __name__ == '__main__':
    unittest.main(verbosity=2)
