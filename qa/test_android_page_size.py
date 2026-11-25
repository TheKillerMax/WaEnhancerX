#!/usr/bin/env python3
"""Host controls for exact legacy ELF/AUXV and modern getconf observations.

All commands are replaced by explicit host fixtures. These tests never invoke
adb, boot an emulator, or establish Android runtime qualification.
"""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import android_emulator_lab_pilot as pilot


def elf64():
    header = bytearray(64)
    header[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', header, 16, 3, 62, 1)
    struct.pack_into('<H', header, 52, 64)
    return bytes(header)


def auxv(pages=4096):
    return struct.pack('<QQQQQQ', 6, pages, 3, 0x400040, 0, 0)


class PageSizeControls(unittest.TestCase):
    def legacy_observation(self, folder, api, *, executable=None, vector=None, fail_stage=None):
        executable = elf64() + b'HOST_EXECUTABLE_FIXTURE' if executable is None else executable
        vector = auxv() if vector is None else vector
        env = {'ADB_SERVER_PORT': '5038', 'WAEX_HOST_FIXTURE': 'yes'}
        calls = []

        def invoke(out, name, command, received_env, **kwargs):
            self.assertEqual(received_env, env)
            self.assertIsNot(kwargs.get('required'), False)
            calls.append(name)
            if name == 'guest-auxv-reader-elf':
                self.assertEqual(command, ['/owned/adb', '-s', 'emulator-5580', 'exec-out',
                                           '/system/bin/cat', '/system/bin/cat'])
                raw = executable
            elif name == 'guest-legacy-auxv':
                self.assertEqual(command, ['/owned/adb', '-s', 'emulator-5580', 'exec-out',
                                           '/system/bin/cat', '/proc/self/auxv'])
                raw = vector
            else:
                raise AssertionError('Legacy path must not invoke getconf or an absence shell: ' + name)
            (out / (name + '.log')).write_bytes(raw)
            if name == fail_stage:
                raise RuntimeError('HOST_TRANSPORT_FAILURE_' + name)
            return {'failure': None, 'returncode': 0}, ''

        with patch.object(pilot, 'invoke', side_effect=invoke):
            observed = pilot.application_page_size(folder, Path('/owned/adb'), env,
                                                   {'sdk': str(api), 'abi': 'x86_64'}, 4096)
        return observed, calls, executable, vector

    def test_all_five_legacy_apis_use_binary_proof_without_getconf(self):
        for api in range(24, 29):
            with self.subTest(api=api), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                (value, report), calls, executable, vector = self.legacy_observation(out, api)
                self.assertEqual(value, '4096')
                self.assertEqual(calls, ['guest-auxv-reader-elf', 'guest-legacy-auxv'])
                self.assertEqual(report['method'], 'legacy_Bionic_sysconf_AT_PAGESZ')
                self.assertIs(report['getconf_requested'], False)
                self.assertEqual(report['api'], api)
                self.assertEqual(report['reader_identity']['full_executable_bytes'], len(executable))
                self.assertEqual(report['reader_identity']['full_executable_sha256'],
                                 hashlib.sha256(executable).hexdigest())
                self.assertEqual((out / 'guest-auxv-reader-elf.log').read_bytes(), executable[:64])
                self.assertEqual(report['reader_elf_header_sha256'], hashlib.sha256(executable[:64]).hexdigest())
                self.assertEqual(report['auxv_sha256'], hashlib.sha256(vector).hexdigest())
                self.assertEqual(report['auxv_bytes'], len(vector))
                policy = json.loads((out / 'guest-page-size-policy.json').read_bytes())
                self.assertEqual(policy['expected_application_page_size_bytes'], 4096)
                self.assertIs(policy['getconf_requested'], False)

    def test_modern_profiles_require_getconf_and_do_not_read_auxv(self):
        lock = json.loads((Path(__file__).parent / 'android_emulator_lab_matrix_lock.json').read_bytes())
        for target, entry in lock['targets'].items():
            api, pages = entry['image']['api'], entry['application_page_size_bytes']
            if api <= 28:
                continue
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                env = {'ADB_SERVER_PORT': '5038'}
                with patch.object(pilot, 'invoke', return_value=({'failure': None, 'returncode': 0},
                                                                 str(pages) + '\n')) as call:
                    value, report = pilot.application_page_size(out, Path('/owned/adb'), env,
                                                               {'sdk': str(api), 'abi': 'x86_64'}, pages)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[2], ['/owned/adb', '-s', 'emulator-5580', 'shell',
                                                        'getconf', 'PAGE_SIZE'])
                self.assertEqual(call.call_args.args[3], env)
                self.assertEqual(value, str(pages))
                self.assertEqual(report, {'method': 'getconf_PAGE_SIZE', 'getconf_requested': True})
                self.assertIs(json.loads((out / 'guest-page-size-policy.json').read_bytes())['getconf_requested'], True)

    def test_modern_command_errors_cannot_fall_back_to_auxv(self):
        for api, pages in ((29, 4096), (35, 16384), (37, 4096)):
            for rc, failure in ((127, None), (255, None), (1, None), (0, 'deadline'), (None, 'spawn')):
                with self.subTest(api=api, rc=rc, failure=failure), tempfile.TemporaryDirectory() as tmp:
                    with patch.object(pilot, 'invoke', return_value=({'failure': failure, 'returncode': rc},
                              '/system/bin/sh: getconf: not found\n')) as call:
                        with self.assertRaisesRegex(RuntimeError, 'getconf command failed'):
                            pilot.application_page_size(Path(tmp), Path('/owned/adb'), {},
                                                        {'sdk': str(api), 'abi': 'x86_64'}, pages)
                    self.assertEqual(call.call_count, 1)

    def test_malformed_or_wrong_getconf_values_are_rejected(self):
        for text in ('', '0', '-4096', '4096\n16384', '4096 bytes', '04096', 'NaN', '16384'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                with patch.object(pilot, 'invoke', return_value=({'failure': None, 'returncode': 0}, text)):
                    with self.assertRaises(RuntimeError):
                        pilot.application_page_size(Path(tmp), Path('/owned/adb'), {},
                                                    {'sdk': '29', 'abi': 'x86_64'}, 4096)

    def test_unreviewed_observation_targets_are_rejected_before_commands(self):
        variants = [('23', 'x86_64', 4096), ('38', 'x86_64', 4096), ('024', 'x86_64', 4096),
                    (24, 'x86_64', 4096), (True, 'x86_64', 4096), ('24', 'arm64-v8a', 4096),
                    ('29', 'x86', 4096), ('24', 'x86_64', 16384), ('28', 'x86_64', 16384),
                    ('29', 'x86_64', 8192), ('29', 'x86_64', '4096'), ('29', 'x86_64', 4096.0),
                    ('29', 'x86_64', True)]
        for api, abi, pages in variants:
            with self.subTest(api=api, abi=abi, pages=pages), tempfile.TemporaryDirectory() as tmp:
                with patch.object(pilot, 'invoke') as call:
                    with self.assertRaises(RuntimeError):
                        pilot.application_page_size(Path(tmp), Path('/owned/adb'), {},
                                                    {'sdk': api, 'abi': abi}, pages)
                call.assert_not_called()

    def test_legacy_transport_errors_remain_fatal(self):
        for name in ('guest-auxv-reader-elf', 'guest-legacy-auxv'):
            with self.subTest(stage=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, 'HOST_TRANSPORT_FAILURE'):
                    self.legacy_observation(Path(tmp), 24, fail_stage=name)

    def test_bad_elf_identity_is_rejected(self):
        variants = {'empty': b'', 'truncated': elf64()[:-1]}
        for name, offset, value in (('magic', 0, b'NOPE'), ('elf32', 4, b'\x01'),
                                    ('big_endian', 5, b'\x02'), ('ident_version', 6, b'\x00'),
                                    ('not_executable', 16, struct.pack('<H', 1)),
                                    ('arm64', 18, struct.pack('<H', 183)),
                                    ('version', 20, struct.pack('<I', 0)),
                                    ('header_size', 52, struct.pack('<H', 52))):
            changed = bytearray(elf64()); changed[offset:offset + len(value)] = value
            variants[name] = bytes(changed)
        for name, executable in variants.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, 'AUXV reader'):
                    self.legacy_observation(Path(tmp), 24, executable=executable)

    def test_bad_auxv_is_rejected(self):
        variants = {'empty': b'', 'truncated': auxv()[:-1], 'oversized': b'\0' * 8208,
                    'no_terminal': auxv()[:-16], 'nonzero_terminal': auxv()[:-8] + struct.pack('<Q', 1),
                    'early_terminal': struct.pack('<QQ', 0, 0) + auxv(),
                    'duplicate_pages': struct.pack('<QQ', 6, 4096) + auxv(),
                    'missing_pages': struct.pack('<QQQQ', 3, 0x400040, 0, 0),
                    'wrong_16k': auxv(16384), 'zero_pages': auxv(0)}
        for name, vector in variants.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(RuntimeError, 'AUXV'):
                    self.legacy_observation(Path(tmp), 24, vector=vector)


if __name__ == '__main__':
    unittest.main()
