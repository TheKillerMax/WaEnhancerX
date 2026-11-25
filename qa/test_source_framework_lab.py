#!/usr/bin/env python3
"""Host counterchecks: no HTTP service, compiler, Android or credentials are used."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

import source_framework_lab as lab


class Response(io.BytesIO):
    status = 200


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b'public dependency bytes'
        self.spec = {'name': 'one.jar', 'url': 'https://repo.maven.apache.org/maven2/one.jar',
                     'bytes': len(self.data), 'max_bytes': len(self.data),
                     'algorithm': 'sha256', 'digest': hashlib.sha256(self.data).hexdigest()}

    def fetch(self, contents, spec=None):
        receipt = {}; calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            return Response(contents)
        lab.acquire(spec or self.spec, self.root / 'one.jar', receipt, opener)
        return receipt, calls

    def test_valid_download_one_request(self):
        receipt, calls = self.fetch(self.data)
        self.assertEqual(len(calls), 1); self.assertEqual(receipt['state'], 'VERIFIED_DOWNLOAD')
        self.assertEqual((self.root / 'one.jar').read_bytes(), self.data)

    def test_cache_hit_makes_no_http_request(self):
        (self.root / 'one.jar').write_bytes(self.data)
        def forbidden(*args, **kwargs):
            self.fail('A verified hit attempted HTTP')
        receipt = {}; lab.acquire(self.spec, self.root / 'one.jar', receipt, forbidden)
        self.assertEqual(receipt['state'], 'VERIFIED_CACHE')

    def test_429_has_one_request_and_preserves_retry_after(self):
        calls = []; receipt = {}
        def limited(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 429, 'Too Many Requests', {'Retry-After': '60'}, None)
        with self.assertRaises(lab.GateError):
            lab.acquire(self.spec, self.root / 'one.jar', receipt, limited)
        self.assertEqual(len(calls), 1); self.assertEqual(receipt['http_status'], 429)
        self.assertEqual(receipt['retry_after'], '60'); self.assertFalse((self.root / 'one.jar').exists())

    def test_wrong_checksum_is_not_cached(self):
        with self.assertRaises(lab.GateError):
            self.fetch(b'x' * len(self.data))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_truncated_download_is_not_cached(self):
        with self.assertRaises(lab.GateError):
            self.fetch(self.data[:-1])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oversized_download_is_not_cached(self):
        with self.assertRaises(lab.GateError):
            self.fetch(self.data + b'x')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unapproved_redirect_rejected(self):
        for url in ('http://repo.maven.apache.org/a', 'https://mirror.invalid/a',
                    'https://user:password@repo.maven.apache.org/a'):
            with self.subTest(url=url), self.assertRaises(lab.GateError):
                lab.checked_url(url)

    def cache(self):
        cache = self.root / 'cache'; cache.mkdir(); (cache / 'one.jar').write_bytes(self.data)
        lab.save(cache / 'verified-cache.json', {'lock_sha256': 'lock', 'files': lab.inventory(cache)})
        return cache

    def test_cache_snapshot_accepts_exact_content(self):
        self.assertEqual(lab.verify_cache(self.cache(), 'lock')['state'], 'VERIFIED_RESTORE')

    def test_cold_empty_cache_is_explicit(self):
        self.assertEqual(lab.verify_cache(self.root / 'empty', 'lock'), {'state': 'COLD', 'files': 0})

    def test_unsealed_nonempty_cache_rejected(self):
        cache = self.root / 'cache'; cache.mkdir(); (cache / 'one.jar').write_bytes(self.data)
        with self.assertRaises(lab.GateError):
            lab.verify_cache(cache, 'lock')

    def test_cache_altered_bytes_rejected(self):
        cache = self.cache(); (cache / 'one.jar').write_bytes(b'x' * len(self.data))
        with self.assertRaises(lab.GateError):
            lab.verify_cache(cache, 'lock')

    def test_cache_missing_file_rejected(self):
        cache = self.cache(); (cache / 'one.jar').unlink()
        with self.assertRaises(lab.GateError):
            lab.verify_cache(cache, 'lock')

    def test_cache_extra_binary_rejected(self):
        cache = self.cache(); (cache / 'two.jar').write_bytes(self.data)
        with self.assertRaises(lab.GateError):
            lab.verify_cache(cache, 'lock')

    def test_cache_other_lock_rejected(self):
        with self.assertRaises(lab.GateError):
            lab.verify_cache(self.cache(), 'other')

    def test_cache_symlink_rejected(self):
        cache = self.cache(); (cache / 'alias').symlink_to(cache / 'one.jar')
        with self.assertRaises(lab.GateError):
            lab.verify_cache(cache, 'lock')

    def report(self, attributes='tests="1" failures="0" errors="0" skipped="0"', cases='<testcase name="real"/>'):
        (self.root / 'TEST-one.xml').write_text('<testsuite ' + attributes + '>' + cases + '</testsuite>')

    def test_exact_junit_case_counts_accepted(self):
        self.report(); self.assertEqual(lab.junit_counts(self.root, 1)['tests'], 1)

    def test_missing_junit_report_rejected(self):
        with self.assertRaises(lab.GateError):
            lab.junit_counts(self.root, 1)

    def test_false_summary_with_missing_cases_rejected(self):
        self.report(cases='')
        with self.assertRaises(lab.GateError):
            lab.junit_counts(self.root, 1)

    def test_hidden_junit_failure_rejected(self):
        self.report(cases='<testcase name="real"><failure>bad</failure></testcase>')
        with self.assertRaises(lab.GateError):
            lab.junit_counts(self.root, 1)

    def test_hidden_junit_skip_rejected(self):
        self.report(cases='<testcase name="real"><skipped/></testcase>')
        with self.assertRaises(lab.GateError):
            lab.junit_counts(self.root, 1)

    def test_429_detector_ignores_hashes_and_test_numbers(self):
        for text in ('artifact 429b3f123', 'tests=429', 'HTTP200', 'Expected value429'):
            self.assertIsNone(lab.RATE_LIMIT.search(text))
        for text in ('status code:429', 'Received status code429 from server', 'HTTP Error429: Too Many Requests', 'HTTP/1.1 429'):
            self.assertIsNotNone(lab.RATE_LIMIT.search(text))

    def test_owned_process_stops_on_first_429_without_second_attempt(self):
        log = self.root / 'run.log'; begin = time.monotonic()
        code = 'import time; print("status code:429 Too Many Requests",flush=True); time.sleep(30); print("SECOND_ATTEMPT")'
        with self.assertRaises(lab.GateError):
            lab.run([sys.executable, '-u', '-c', code], self.root, dict(os.environ), log, self.root, timeout=10)
        self.assertLess(time.monotonic() - begin, 5)
        receipt = json.loads(log.with_suffix('.command.json').read_text())
        self.assertIsNotNone(receipt['http_429']); self.assertNotIn('SECOND_ATTEMPT', log.read_text())

    def test_nonzero_stage_exit_is_failure(self):
        with self.assertRaises(lab.GateError):
            lab.run([sys.executable, '-c', 'raise SystemExit(7)'], self.root, dict(os.environ),
                    self.root / 'run.log', self.root, timeout=5)

    def test_owned_child_in_new_session_is_stopped_too(self):
        log = self.root / 'run.log'
        code = ('import subprocess,sys,time; '
                'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],start_new_session=True); '
                'print("CHILD="+str(child.pid),flush=True); time.sleep(0.6); '
                'print("status code:429 Too Many Requests",flush=True); time.sleep(30)')
        with self.assertRaises(lab.GateError):
            lab.run([sys.executable, '-u', '-c', code], self.root, dict(os.environ), log, self.root, timeout=5)
        pid = int(log.read_text().split('CHILD=')[1].splitlines()[0])
        status = Path('/proc', str(pid), 'status')
        if status.exists():
            # An adopted zombie is already stopped and cannot perform a retry.
            state = next(line for line in status.read_text().splitlines() if line.startswith('State:'))
            self.assertIn('Z', state)

    def test_successful_process_is_not_mistaken_for_429(self):
        result = lab.run([sys.executable, '-c', 'print("tests=429")'], self.root, dict(os.environ),
                         self.root / 'run.log', self.root, timeout=5)
        self.assertEqual(result['exit_code'], 0)

    def test_failure_preserves_explicit_blocked_stages(self):
        lock = Path(lab.__file__).with_name('source_framework_lab_lock.json')
        runner = lab.Lab(self.root, self.root / 'cache', self.root / 'out', lock)
        with patch.object(runner, 'preflight', side_effect=lab.GateError('dependency unavailable')):
            self.assertEqual(runner.execute(), 1)
        states = runner.result['stages']
        self.assertEqual(states['source-and-tools']['state'], 'FAIL')
        self.assertTrue(all(states[name]['state'] == 'BLOCKED' for name in lab.STAGES[1:]))

    def test_original_commands_have_no_sdk_selection_or_negative_acceptance(self):
        lock = Path(lab.__file__).with_name('source_framework_lab_lock.json')
        runner = lab.Lab(self.root, self.root / 'cache', self.root / 'out', lock); runner.aapt2 = self.root / 'aapt2'
        commands = []
        with patch.object(runner, 'command', side_effect=lambda name, command, *a, **kw: commands.append(list(map(str, command)))), \
             patch.object(lab, 'validate_result', return_value={'test': 'command-only-control'}):
            for name in ('presence', 'presence-companion', 'store', 'dispatch', 'runtime', 'interface', 'stability'):
                runner.suite(name)
        self.assertEqual(len(commands), 7)
        for command in commands:
            self.assertNotIn('--sdk', command); self.assertNotIn('--expect-assertion-failures', command)
            self.assertFalse(any('enabledSdks' in part for part in command))
        self.assertIn('--mutations', commands[0]); self.assertNotIn('--mode', commands[-1])

    def test_immediate_detached_child_is_reaped_without_sampling_delay(self):
        log = self.root / 'run.log'
        code = ('import os,subprocess,sys; from pathlib import Path; '
                'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],start_new_session=True); '
                'start=Path("/proc",str(child.pid),"stat").read_text().rsplit(")",1)[1].split()[19]; '
                'print("CHILD="+str(child.pid)+"|"+start,flush=True); os._exit(0)')
        try:
            receipt = lab.run([sys.executable, '-u', '-c', code], self.root, dict(os.environ),
                              log, self.root, timeout=5)
            pid, started = log.read_text().split('CHILD=')[1].splitlines()[0].split('|')
            self.assertIsNone(lab.process_identity(int(pid)))
            self.assertTrue(receipt['cleanup']['all_owned_processes_reaped'])
        finally:
            if log.exists() and 'CHILD=' in log.read_text():
                pid, started = log.read_text().split('CHILD=')[1].splitlines()[0].split('|')
                pid = int(pid); identity = lab.process_identity(pid)
                if identity and identity[1] == started:
                    os.kill(pid, 9)
                    try:
                        os.waitpid(pid, 0)
                    except ChildProcessError:
                        pass

    def test_existing_child_is_not_adopted_or_signalled_as_this_command(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 start_new_session=True)
        try:
            with self.assertRaises(lab.GateError):
                lab.run([sys.executable, '-c', 'raise SystemExit(0)'], self.root, dict(os.environ),
                        self.root / 'run.log', self.root, timeout=5)
            self.assertIsNone(child.poll())
        finally:
            child.kill(); child.wait(timeout=5)

    def rewritten_log(self, replace):
        target = self.root / 'dependency.log'
        code = ('import time; from pathlib import Path; '
                'p=Path(' + repr(str(target)) + '); p.write_text("A"*8192); time.sleep(0.6); ')
        if replace:
            code += 'q=p.with_suffix(".new"); q.write_text("HTTP Error429: Too Many Requests"); q.replace(p); '
        else:
            code += 'p.write_text("HTTP Error429: Too Many Requests"); '
        code += 'time.sleep(30)'
        begin = time.monotonic()
        with self.assertRaises(lab.GateError):
            lab.run([sys.executable, '-u', '-c', code], self.root, dict(os.environ),
                    self.root / 'run.log', self.root, timeout=10)
        receipt = json.loads((self.root / 'run.command.json').read_text())
        self.assertIsNotNone(receipt['http_429'])
        self.assertEqual(receipt['http_429']['log'], str(target))
        self.assertLess(time.monotonic() - begin, 5)

    def test_truncated_log_does_not_hide_http429(self):
        self.rewritten_log(False)

    def test_replaced_log_does_not_hide_http429(self):
        self.rewritten_log(True)

    def test_http429_on_immediate_process_exit_is_still_failure(self):
        log = self.root / 'run.log'
        with self.assertRaises(lab.GateError):
            lab.run([sys.executable, '-c', 'print("HTTP Error429: Too Many Requests")'],
                    self.root, dict(os.environ), log, self.root, timeout=5)
        receipt = json.loads(log.with_suffix('.command.json').read_text())
        self.assertIsNotNone(receipt['http_429'])



if __name__ == '__main__':
    unittest.main(verbosity=2)
