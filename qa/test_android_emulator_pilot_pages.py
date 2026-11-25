#!/usr/bin/env python3
"""Host controls for page-size fallback and bounded guest readiness; no ADB or emulator execution."""
import os
import json
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
        self.assertEqual(pilot.legacy_auxv_page_size(elf64(), auxv((3, 123), (6, 4096), (0, 0))), 4096)

    def test_rejects_invalid_binary_inputs(self):
        good = auxv((3, 123), (6, 4096), (0, 0))
        cases = {
            'truncated header': (elf64()[:-1], good),
            'wrong class': (elf64()[:4] + b'\x01' + elf64()[5:], good),
            'wrong endian': (elf64()[:5] + b'\x02' + elf64()[6:], good),
            'wrong machine': (elf64()[:18] + b'\xb7\x00' + elf64()[20:], good),
            'not ELF': (bytes(64), good),
            'observed old head error': (b'head: not integer: c\n', good),
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
                pilot.legacy_auxv_page_size(header, raw)

    def run_reader(self, api='24', abi='x86_64', expected=4096, rc=127,
                   text='/system/bin/sh: getconf: not found\n', failure=None, raw=None, absent=True):
        commands = []
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)

            def invoke(output, name, command, env, **kwargs):
                commands.append(command)
                if name == 'guest-application_page_size_bytes':
                    return {'returncode': rc, 'failure': failure}, text
                if name == 'guest-getconf-absent':
                    if not absent:
                        raise RuntimeError('getconf exists or resolves')
                    return {'returncode': 0, 'failure': None}, ''
                if name == 'guest-auxv-reader-elf':
                    (output / (name + '.log')).write_bytes(elf64() + b'synthetic executable body')
                elif name == 'guest-legacy-auxv':
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
        self.assertEqual(result[1]['reader_identity']['retained_bytes'], 64)
        self.assertGreater(result[1]['reader_identity']['full_executable_bytes'], 64)
        self.assertEqual(commands[2][3:], ['exec-out', '/system/bin/cat', '/system/bin/cat'])
        self.assertEqual(commands[3][3:], ['exec-out', '/system/bin/cat', '/proc/self/auxv'])
        self.assertTrue(all(command[1:3] == ['-s', 'emulator-5580'] for command in commands))

    def test_legacy_platform_scope_requires_explicit_getconf_absence(self):
        for api in ('24', '25', '26', '27', '28'):
            with self.subTest(api=api):
                result, commands = self.run_reader(api=api)
                self.assertEqual(result[0], '4096')
                self.assertEqual(result[1]['api'], int(api))
                self.assertIn('command -v getconf', commands[1][-1])
                with self.assertRaises(RuntimeError):
                    self.run_reader(api=api, absent=False)

    def test_ambiguous_shell_not_found_requires_a_separate_absence_check(self):
        text = '/system/bin/sh: getconf: inaccessible or not found\n'
        result, _ = self.run_reader(api='26', text=text)
        self.assertEqual(result[0], '4096')
        with self.assertRaises(RuntimeError):
            self.run_reader(api='26', text=text, absent=False)

    def test_modern_16k_requires_getconf(self):
        result, commands = self.run_reader(api='35', expected=16384, rc=0, text='16384\n')
        self.assertEqual(result, ('16384', {'method': 'getconf_PAGE_SIZE'}))
        self.assertEqual(len(commands), 1)

    def test_refuses_other_failures_or_wrong_values(self):
        cases = [dict(api='35', expected=16384), dict(api='29'), dict(abi='arm64-v8a'),
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
        actual = pilot.legacy_auxv_page_size(header, Path('/proc/self/auxv').read_bytes())
        self.assertEqual(actual, os.sysconf('SC_PAGE_SIZE'))



class GuestReadinessControls(unittest.TestCase):
    def sample(self, elapsed, pid='700', user='RUNNING_UNLOCKED'):
        values = {'boot': '1', 'pid_before': pid, 'pid_after': pid,
                  'package': 'package:/system/framework/framework-res.apk', 'user': user}
        return {'elapsed_ms': elapsed, 'checks': {key: {'returncode': 0, 'failure': None, 'text': value}
                                                 for key, value in values.items()}}

    def receipt(self):
        return {'schema_version': 1, 'status': 'PASS', 'horizon_ms': 15000,
                'future_stability_claimed': False, 'system_server_pid': '700',
                'observations': [self.sample(1000), self.sample(8500), self.sample(16000)]}

    def exercise(self, mode):
        clock = [0.0]
        calls = []
        class OwnedProcess:
            def poll(self):
                return None
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); log = out / 'emulator.log'; log.write_bytes(b'')
            def invoke(output, name, command, env, **kwargs):
                calls.append((name, command, kwargs))
                index, key = name.removeprefix('guest-ready-').split('-', 1)
                index = int(index); row = self.sample(0)['checks'][key].copy()
                if mode == 'transient':
                    if index < 2 and key == 'package':
                        row.update(returncode=20, text="cmd: Can't find service: package")
                    if index == 2 and key == 'user':
                        row['text'] = 'RUNNING_UNLOCKING'
                if mode == 'pid_change' and index >= 3 and key.startswith('pid_'):
                    row['text'] = '900'
                if mode == 'locked' and key == 'user':
                    row['text'] = 'RUNNING_LOCKED'
                if mode == 'broken_pipe' and key == 'package':
                    row.update(returncode=20, text='cmd: Failure calling service package: Broken pipe (32)')
                if mode == 'ambiguous_timeout' and key == 'package':
                    row['failure'] = 'transport timeout'
                if mode == 'multiple_pids' and key.startswith('pid_'):
                    row['text'] = '700 701'
                clock[0] += 0.05
                return {'returncode': row['returncode'], 'failure': row['failure']}, row['text']
            with patch.object(pilot, 'invoke', invoke), patch.object(pilot, 'guard_space', return_value=32 * 1024**3), \
                    patch.object(pilot.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(pilot.time, 'sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay)):
                if mode in ('locked', 'broken_pipe', 'ambiguous_timeout', 'multiple_pids'):
                    with self.assertRaisesRegex(RuntimeError, 'deadline'):
                        pilot.wait_for_guest_ready(out, '/sdk/adb', {}, OwnedProcess(), out, log, 0)
                    result = json.loads((out / 'guest-readiness.json').read_text())
                    self.assertEqual(result['status'], 'BLOCKED')
                    self.assertLessEqual(clock[0], 420.25)
                else:
                    result = pilot.wait_for_guest_ready(out, '/sdk/adb', {}, OwnedProcess(), out, log, 0)
                    self.assertEqual(result, json.loads((out / 'guest-readiness.json').read_text()))
        self.assertTrue(all(command[1:4] == ['-s', 'emulator-5580', 'shell'] for _, command, _ in calls))
        self.assertTrue(all(command[4:] in list(pilot.READY_COMMANDS.values()) for _, command, _ in calls))
        return result

    def test_waits_for_package_and_user_beyond_boot_property(self):
        result = self.exercise('transient')
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['future_stability_claimed'])
        self.assertGreaterEqual(result['observations'][-1]['elapsed_ms'], 30000)
        self.assertEqual(result['observations'][0]['checks']['package']['returncode'], 20)
        self.assertEqual(result['observations'][2]['checks']['user']['text'], 'RUNNING_UNLOCKING')

    def test_pid_change_restarts_observation_horizon(self):
        result = self.exercise('pid_change')
        self.assertEqual(result['system_server_pid'], '900')
        tail = [row for row in result['observations'] if pilot.ready_pid(row) == '900']
        self.assertGreaterEqual(tail[-1]['elapsed_ms'] - tail[0]['elapsed_ms'], 15000)
        self.assertGreaterEqual(result['observations'][-1]['elapsed_ms'], 30000)

    def test_locked_or_ambiguous_guest_hits_total_deadline(self):
        for mode in ('locked', 'broken_pipe', 'ambiguous_timeout', 'multiple_pids'):
            with self.subTest(mode=mode):
                self.exercise(mode)

    def test_receipt_rejects_false_pass_short_horizon_and_restart(self):
        self.assertEqual(pilot.validate_guest_readiness(self.receipt())['status'], 'PASS')
        mutations = [
            lambda value: value.update(status='BLOCKED'),
            lambda value: value.update(future_stability_claimed=True),
            lambda value: value.update(observations=value['observations'][-1:]),
            lambda value: value['observations'][-1].update(elapsed_ms=15999),
            lambda value: value['observations'][1].update(elapsed_ms=1000),
            lambda value: value['observations'][-1].update(elapsed_ms=420000),
            lambda value: value['observations'][1]['checks']['pid_before'].update(text='900'),
            lambda value: value['observations'][-1]['checks']['user'].update(text='RUNNING_UNLOCKED extra'),
            lambda value: value['observations'][-1]['checks']['package'].update(returncode=20),
            lambda value: value['observations'][-1]['checks']['package'].update(failure='timeout'),
        ]
        for mutate in mutations:
            value = self.receipt(); mutate(value)
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                pilot.validate_guest_readiness(value)

    def test_diagnostics_preserve_errors_and_total_budget(self):
        clock, calls = [0.0], []
        class OwnedProcess:
            def poll(self):
                return None
        with tempfile.TemporaryDirectory() as directory:
            def invoke(out, name, command, env, **kwargs):
                calls.append((command, kwargs['timeout']))
                clock[0] += kwargs['timeout']
                if len(calls) == 1:
                    raise OSError('original diagnostic failure')
                return {'returncode': 20, 'failure': None}, 'service unavailable'
            with patch.object(pilot, 'invoke', invoke), \
                    patch.object(pilot.time, 'monotonic', side_effect=lambda: clock[0]):
                value = pilot.capture_guest_diagnostics(Path(directory), '/sdk/adb', {}, OwnedProcess())
            self.assertEqual(value['status'], 'PARTIAL')
            self.assertIn('OSError: original diagnostic failure', value['errors'][0])
            self.assertLessEqual(value['elapsed_seconds'], 45)
            self.assertTrue(all(timeout <= 6 for _, timeout in calls))
            self.assertTrue(all(command[1:3] == ['-s', 'emulator-5580'] for command, _ in calls))
            self.assertFalse(any('install' in command or 'root' in command or 'su' in command for command, _ in calls))


        clock[0] = 0.0; calls.clear()
        def delayed_close(out, name, command, env, **kwargs):
            calls.append(name)
            clock[0] += kwargs['timeout'] + (20.5 if len(calls) == 8 else 0)
            return {'returncode': -9 if len(calls) == 8 else 0,
                    'failure': 'deadline and final child closure' if len(calls) == 8 else None}, ''
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot, 'invoke', delayed_close), \
                patch.object(pilot.time, 'monotonic', side_effect=lambda: clock[0]):
            value = pilot.capture_guest_diagnostics(Path(directory), '/sdk/adb', {}, OwnedProcess())
        self.assertEqual(value['status'], 'PARTIAL')
        self.assertEqual(value['acquisition_budget_seconds'], 45)
        self.assertEqual(value['elapsed_seconds'], 65.5)

    def test_diagnostics_do_not_read_an_exited_owned_emulator(self):
        class ExitedProcess:
            def poll(self):
                return 1
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot, 'invoke') as invoke:
            value = pilot.capture_guest_diagnostics(Path(directory), '/sdk/adb', {}, ExitedProcess())
            self.assertEqual(value['status'], 'PARTIAL')
            invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
