#!/usr/bin/env python3
"""Host controls for the API 24 page-size fallback; no ADB or emulator execution."""
import os
from pathlib import Path
import platform
import struct
import tempfile
import unittest
from unittest.mock import patch

import android_emulator_lab_pilot as pilot


def elf64():
    raw = bytearray(64)
    raw[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', raw, 16, 3, 62, 1)
    struct.pack_into('<H', raw, 52, 64)
    return bytes(raw)


def auxv(*pairs):
    return b''.join(struct.pack('<QQ', *pair) for pair in pairs)


class PageSizeControls(unittest.TestCase):
    def test_valid_api24_elf_auxv(self):
        self.assertEqual(pilot.api24_auxv_page_size(elf64(), auxv((3, 123), (6, 4096), (0, 0))), 4096)

    def test_rejects_invalid_binary_inputs(self):
        good = auxv((3, 123), (6, 4096), (0, 0))
        cases = {
            'truncated header': (elf64()[:-1], good),
            'wrong class': (elf64()[:4] + b'\x01' + elf64()[5:], good),
            'wrong endian': (elf64()[:5] + b'\x02' + elf64()[6:], good),
            'wrong machine': (elf64()[:18] + b'\xb7\x00' + elf64()[20:], good),
            'not ELF': (bytes(64), good),
            'empty AUXV': (elf64(), b''),
            'truncated AUXV': (elf64(), good[:-1]),
            'oversized AUXV': (elf64(), bytes(8208)),
            'missing terminator': (elf64(), good[:-16]),
            'early terminator': (elf64(), auxv((0, 0), (6, 4096), (0, 0))),
            'duplicate page tag': (elf64(), auxv((6, 4096), (6, 4096), (0, 0))),
            'duplicate other tag': (elf64(), auxv((3, 1), (3, 2), (6, 4096), (0, 0))),
            'missing page tag': (elf64(), auxv((3, 123), (0, 0))),
            'zero page size': (elf64(), auxv((6, 0), (0, 0))),
            '16k is not this fallback': (elf64(), auxv((6, 16384), (0, 0))),
        }
        for label, (header, raw) in cases.items():
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                pilot.api24_auxv_page_size(header, raw)

    def run_reader(self, api='24', abi='x86_64', expected=4096, rc=127,
                   text='/system/bin/sh: getconf: not found\n', failure=None, raw=None):
        commands = []
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)

            def invoke(output, name, command, env, **kwargs):
                commands.append(command)
                if name == 'guest-application_page_size_bytes':
                    return {'returncode': rc, 'failure': failure}, text
                if name == 'guest-auxv-reader-elf':
                    (output / (name + '.log')).write_bytes(elf64())
                elif name == 'guest-api24-auxv':
                    (output / (name + '.log')).write_bytes(raw if raw is not None else auxv((6, 4096), (0, 0)))
                else:
                    raise AssertionError('Unexpected command: ' + name)
                return {'returncode': 0, 'failure': None}, ''

            with patch.object(pilot, 'invoke', invoke):
                result = pilot.application_page_size(out, '/sdk/adb', {}, {'sdk': api, 'abi': abi}, expected)
        return result, commands

    def test_observed_missing_getconf_uses_raw_exact_reader(self):
        result, commands = self.run_reader()
        self.assertEqual(result[0], '4096')
        self.assertEqual(result[1]['pointer_bytes'], 8)
        self.assertEqual(commands[1][3:], ['exec-out', '/system/bin/head', '-c', '64', '/system/bin/cat'])
        self.assertEqual(commands[2][3:], ['exec-out', '/system/bin/cat', '/proc/self/auxv'])
        self.assertTrue(all(command[1:3] == ['-s', 'emulator-5580'] for command in commands))

    def test_modern_16k_requires_getconf(self):
        result, commands = self.run_reader(api='35', expected=16384, rc=0, text='16384\n')
        self.assertEqual(result, ('16384', {'method': 'getconf_PAGE_SIZE'}))
        self.assertEqual(len(commands), 1)

    def test_refuses_other_failures_or_wrong_values(self):
        cases = [dict(api='35', expected=16384), dict(api='25'), dict(abi='arm64-v8a'),
                 dict(expected=16384), dict(rc=1), dict(failure='timeout'),
                 dict(text='permission denied'), dict(rc=0, text=''),
                 dict(rc=0, text='4096\n16384'), dict(api='35', expected=16384, rc=0, text='4096'),
                 dict(raw=auxv((6, 16384), (0, 0)))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                self.run_reader(**case)

    @unittest.skipUnless(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'Linux host comparison only')
    def test_real_host_auxv_matches_sysconf_not_android_evidence(self):
        with Path('/proc/self/exe').open('rb') as stream:
            header = stream.read(64)
        actual = pilot.api24_auxv_page_size(header, Path('/proc/self/auxv').read_bytes())
        self.assertEqual(actual, os.sysconf('SC_PAGE_SIZE'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
