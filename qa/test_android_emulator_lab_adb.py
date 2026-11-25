#!/usr/bin/env python3
"""Host controls for exact ADB recovery; no SDK, server, emulator or device."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import android_emulator_lab_adb as adb
import android_emulator_lab_pilot as pilot


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


PAYLOADS = {'adb': b'reviewed-adb', 'lib64/libc++.so': b'reviewed-library',
            'NOTICE.txt': b'reviewed-notice', 'source.properties': b'Pkg.Revision=37.0.1\n'}
PINS = {name: (len(raw), sha(raw), 0o755 if name in ('adb', 'lib64/libc++.so') else 0o644)
        for name, raw in PAYLOADS.items()}


def archive_bytes(*, omit=None, duplicate=None, mode_name=None, changed=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, raw in PAYLOADS.items():
            if name == omit:
                continue
            info = zipfile.ZipInfo('platform-tools/' + name)
            info.create_system = 3
            info.external_attr = ((0o120777 if name == mode_name else 0o100000 | PINS[name][2]) << 16)
            archive.writestr(info, raw[::-1] if name == changed else raw)
            if name == duplicate:
                archive.writestr(info, raw)
        # Never extract an unselected path, even if it appears in the verified ZIP.
        archive.writestr('../unselected-escape', b'must not be written')
    return stream.getvalue()


class AdbRecoveryControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.out = self.work / 'reports'
        self.out.mkdir()
        self.raw = archive_bytes()
        for key, value in {'MEMBERS': PINS, 'ARCHIVE_BYTES': len(self.raw), 'ARCHIVE_SHA256': sha(self.raw)}.items():
            patched = patch.object(adb, key, value)
            patched.start()
            self.addCleanup(patched.stop)

    def test_exact_members_only_with_library_notice_and_modes(self):
        destination = self.work / 'owned'
        result = adb.extract_archive(self.raw, destination)
        self.assertEqual(set(result), set(PAYLOADS))
        self.assertEqual({p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}, set(PAYLOADS))
        self.assertFalse((self.work / 'unselected-escape').exists())
        self.assertEqual(result, adb.installed_identity(destination))

    def test_wrong_archive_bytes_or_digest_fail_before_writing(self):
        for index, raw in enumerate((self.raw[:-1], self.raw + b'x', b'x' + self.raw[1:])):
            destination = self.work / str(index)
            with self.subTest(index=index), self.assertRaisesRegex(RuntimeError, 'size|SHA256'):
                adb.extract_archive(raw, destination)
            self.assertFalse(destination.exists())

    def test_bad_selected_member_rejected_even_with_valid_archive_digest(self):
        for index, kwargs in enumerate(({'omit': 'adb'}, {'duplicate': 'adb'},
                                        {'mode_name': 'lib64/libc++.so'}, {'changed': 'NOTICE.txt'})):
            raw = archive_bytes(**kwargs)
            destination = self.work / str(index)
            with self.subTest(kwargs=kwargs), patch.object(adb, 'ARCHIVE_BYTES', len(raw)), \
                    patch.object(adb, 'ARCHIVE_SHA256', sha(raw)), self.assertRaises(RuntimeError):
                adb.extract_archive(raw, destination)
            self.assertFalse(destination.exists())

    def test_existing_or_symlink_destination_is_not_overwritten(self):
        existing = self.work / 'existing'
        existing.mkdir()
        (existing / 'kept').write_bytes(b'untouched')
        link = self.work / 'link'
        link.symlink_to(existing, target_is_directory=True)
        for destination in (existing, link):
            with self.subTest(destination=destination), self.assertRaises(RuntimeError):
                adb.extract_archive(self.raw, destination)
        self.assertEqual((existing / 'kept').read_bytes(), b'untouched')

    def test_readback_rejects_changed_library_and_symlink(self):
        destination = self.work / 'owned'
        adb.extract_archive(self.raw, destination)
        library = destination / 'lib64/libc++.so'
        library.write_bytes(b'changed-library!')
        with self.assertRaises(RuntimeError):
            adb.installed_identity(destination)
        library.unlink()
        outside = self.work / 'outside-library'
        outside.write_bytes(PAYLOADS['lib64/libc++.so'])
        outside.chmod(0o755)
        library.symlink_to(outside)
        with self.assertRaises(RuntimeError):
            adb.installed_identity(destination)

    def test_download_is_bounded_and_bad_http_identity_blocks(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': str(len(self.raw))}
            def geturl(self):
                return adb.URL
        with patch.object(adb, 'build_opener') as opener:
            opener.return_value.open.return_value = Response(self.raw)
            self.assertEqual(adb.download_archive(), self.raw)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 20)
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url, adb.URL)
        for attribute, value in (('status', 206), ('headers', {'Content-Length': '999'}),
                                  ('geturl', lambda _: 'https://example.invalid/other')):
            response = Response(self.raw)
            if attribute == 'geturl':
                response.geturl = lambda: value(None)
            else:
                setattr(response, attribute, value)
            with self.subTest(attribute=attribute), patch.object(adb, 'build_opener') as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(RuntimeError):
                    adb.download_archive()
        with self.assertRaisesRegex(RuntimeError, 'redirected'):
            adb.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid/')

    def tools(self, sdk_adb):
        sdk = self.work / 'sdk'
        (sdk / 'platform-tools').mkdir(parents=True)
        tools = {'adb': sdk / 'platform-tools/adb'}
        tools['adb'].write_bytes(sdk_adb)
        for name in ('java', 'sdkmanager', 'emulator'):
            tools[name] = sdk / name
            tools[name].write_bytes(name.encode())
        pins = {name: sha(path.read_bytes()) for name, path in tools.items()}
        pins['adb'] = PINS['adb'][1]
        return sdk, tools, pins

    def test_preinstalled_reviewed_adb_never_downloads(self):
        sdk, tools, pins = self.tools(PAYLOADS['adb'])
        with patch.object(pilot, 'invoke', side_effect=AssertionError('unexpected acquisition')):
            selected, observed, owned = pilot.reviewed_tools(self.work, self.out, tools, {}, pins)
        self.assertIsNone(owned)
        self.assertEqual(selected['adb'], observed)
        pilot.unchanged_adb(sdk, observed, owned)

    def test_changed_sdk_adb_selects_exact_owned_bytes_and_preserves_sdk(self):
        sdk, tools, pins = self.tools(b'new-runner-adb')
        def acquire(out, name, command, env, timeout):
            self.assertEqual(name, 'acquire-reviewed-adb')
            self.assertEqual(timeout, 90)
            self.assertEqual(command[command.index('--out') + 1], str(self.work / 'reviewed-platform-tools'))
            adb.extract_archive(self.raw, self.work / 'reviewed-platform-tools')
        with patch.object(pilot, 'invoke', side_effect=acquire) as called:
            selected, observed, owned = pilot.reviewed_tools(self.work, self.out, tools, {}, pins)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(selected['adb']['sha256'], pins['adb'])
        self.assertNotEqual(selected['adb']['path'], observed['path'])
        self.assertEqual((sdk / 'platform-tools/adb').read_bytes(), b'new-runner-adb')
        pilot.unchanged_adb(sdk, observed, owned)
        (owned / 'lib64/libc++.so').write_bytes(b'tampered')
        with self.assertRaises(RuntimeError):
            pilot.unchanged_adb(sdk, observed, owned)

    def test_other_tool_or_unknown_adb_pin_blocks_before_download_and_records_observation(self):
        _, tools, pins = self.tools(b'new-runner-adb')
        for name in ('java', 'sdkmanager', 'emulator', 'adb'):
            changed = dict(pins, **{name: '0' * 64})
            with self.subTest(name=name), patch.object(pilot, 'invoke') as called:
                with self.assertRaises(RuntimeError):
                    pilot.reviewed_tools(self.work, self.out, tools.copy(), {}, changed)
                called.assert_not_called()
                observed = json.loads((self.out / 'tool-identities-observed.json').read_bytes())
                self.assertEqual(observed['adb']['sha256'], sha(b'new-runner-adb'))

    def test_acquisition_failure_and_invalid_output_cannot_reach_selection(self):
        _, tools, pins = self.tools(b'new-runner-adb')
        for effect in (RuntimeError('bounded acquisition failed'), None):
            with self.subTest(effect=effect), patch.object(pilot, 'invoke', side_effect=effect):
                with self.assertRaises(RuntimeError):
                    pilot.reviewed_tools(self.work, self.out, tools.copy(), {}, pins)
                self.assertFalse((self.out / 'adb-selection.json').exists())

    def test_original_sdk_mutation_is_still_rejected_after_selection(self):
        sdk, tools, pins = self.tools(PAYLOADS['adb'])
        _, observed, owned = pilot.reviewed_tools(self.work, self.out, tools, {}, pins)
        (sdk / 'platform-tools/adb').write_bytes(b'changed-after-selection')
        with self.assertRaisesRegex(RuntimeError, 'Preinstalled SDK ADB changed'):
            pilot.unchanged_adb(sdk, observed, owned)


if __name__ == '__main__':
    unittest.main()
