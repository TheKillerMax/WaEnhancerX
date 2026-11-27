#!/usr/bin/env python3
"""Exercise the single-artifact DexKit bootstrap with loopback transport fixtures.

The small synthetic archive is not DexKit. Real pinned-byte compilation remains
the separate 83-check status-style fixture and is never replaced by these tests.
"""
import argparse
import datetime
from email.utils import format_datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
import warnings
import zipfile

import prepare_dexkit as bootstrap

OUT = None
BODY = b'synthetic classes.jar transport fixture\n'


def digest(body):
    return hashlib.sha256(body).hexdigest()


def archive(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as output, warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        for name, data in members:
            output.writestr(zipfile.ZipInfo(name), data)
    return stream.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append({'path': self.path, 'time': time.monotonic()})
        code, headers, body = self.server.responses.pop(0) if self.server.responses else (200, {}, self.server.body)
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            if self.server.slow:
                for byte in body:
                    self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(0.05)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


class DexKitPreparationControls(unittest.TestCase):
    def setUp(self):
        self.work = OUT / self._testMethodName; self.work.mkdir()
        self.cache, self.report = self.work / 'cache', self.work / 'receipt.json'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.requests, self.server.responses, self.server.slow = [], [], False
        self.server.body = archive([('classes.jar', BODY)])
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.aar = dict(bootstrap.AAR, bytes=len(self.server.body), sha256=digest(self.server.body),
                        url=f'http://127.0.0.1:{self.server.server_port}/dexkit.aar')
        self.jar = dict(bootstrap.JAR, bytes=len(BODY), sha256=digest(BODY))
        for item in (mock.patch.object(bootstrap, 'AAR', self.aar),
                     mock.patch.object(bootstrap, 'JAR', self.jar),
                     mock.patch.object(bootstrap.transport, 'load_lock', side_effect=AssertionError('No framework graph')),
                     mock.patch.object(bootstrap.transport, 'prepare', side_effect=AssertionError('No SDK preparation'))):
            item.start(); self.addCleanup(item.stop)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
        (self.work / 'http-requests.json').write_text(json.dumps(self.server.requests, indent=2) + '\n')

    def prepare(self, **kwargs):
        return bootstrap.prepare(self.cache, self.report, **kwargs)

    def receipt(self):
        return json.loads(self.report.read_bytes())

    def assert_no_jar_or_partial(self):
        self.assertFalse((self.cache / self.jar['name']).exists())
        self.assertEqual([], list(self.cache.glob('.sdk-download-*')))
        self.assertFalse(self.receipt()['accepted'])

    def test_cold_download_extracts_then_verified_cache_makes_zero_requests(self):
        result = self.prepare(timeout=10)
        self.assertTrue(result['accepted'])
        self.assertEqual(1, result['network_requests'])
        self.assertFalse(result['framework_graph_resolved'])
        self.assertEqual(BODY, (self.cache / self.jar['name']).read_bytes())
        self.report = self.work / 'cached.json'
        result = self.prepare(offline=True)
        self.assertTrue(result['accepted'])
        self.assertEqual(0, result['network_requests'])
        self.assertEqual(1, len(self.server.requests))

    def test_429_respects_seconds_then_downloads_same_pinned_archive(self):
        self.server.responses = [(429, {'Retry-After': '1'}, b'rate limited')]
        result = self.prepare(timeout=10)
        attempts = result['files'][0]['attempts']
        self.assertEqual([429, 200], [row['http_status'] for row in attempts])
        self.assertEqual(1.0, attempts[0]['wait_seconds'])
        self.assertGreaterEqual(self.server.requests[1]['time'] - self.server.requests[0]['time'], 1.0)
        self.assertTrue(result['accepted'])

    def test_long_or_malformed_retry_after_stops_with_failure_receipt(self):
        date = format_datetime(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1), usegmt=True)
        for index, value in enumerate(('120', date, 'not-a-date')):
            with self.subTest(value=value):
                self.cache, self.report = self.work / f'cache-{index}', self.work / f'receipt-{index}.json'
                self.server.responses = [(429, {'Retry-After': value}, b'rate limited')]
                with self.assertRaises(RuntimeError):
                    self.prepare(timeout=10)
                self.assertEqual(1, self.receipt()['network_requests'])
                self.assert_no_jar_or_partial()
                attempt = self.receipt()['files'][0]['attempts'][0]
                if index < 2:
                    self.assertEqual('retry_deferred_beyond_budget', attempt['status'])
                else:
                    self.assertFalse(attempt['retryable'])
        self.assertEqual(3, len(self.server.requests))

    def test_transient_attempt_limit_does_not_publish_or_claim_tests(self):
        self.server.responses = [(503, {}, b'unavailable')] * 3
        with self.assertRaises(RuntimeError):
            self.prepare(timeout=10)
        self.assertEqual(3, self.receipt()['network_requests'])
        self.assertEqual(3, len(self.server.requests))
        self.assert_no_jar_or_partial()

    def test_nontransient_response_and_corrupt_download_are_not_retried(self):
        cases = [(404, b'missing'), (200, b'X' * len(self.server.body)), (200, self.server.body + b'oversize')]
        for index, (status, body) in enumerate(cases):
            with self.subTest(status=status, bytes=len(body)):
                self.cache, self.report = self.work / f'cache-{index}', self.work / f'receipt-{index}.json'
                self.server.responses = [(status, {}, body)]
                with self.assertRaises((RuntimeError, ValueError)):
                    self.prepare(timeout=10)
                self.assertEqual(1, self.receipt()['network_requests'])
                self.assertFalse((self.cache / self.aar['name']).exists())
                self.assert_no_jar_or_partial()
        self.assertEqual(3, len(self.server.requests))

    def test_bad_existing_inputs_are_preserved_without_network_fallback(self):
        for index, item in enumerate((self.aar, self.jar)):
            with self.subTest(name=item['name']):
                self.cache, self.report = self.work / f'cache-{index}', self.work / f'receipt-{index}.json'
                self.cache.mkdir()
                bad = self.cache / item['name']; bad.write_bytes(b'corrupt cached bytes')
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    self.prepare(timeout=10)
                self.assertEqual(b'corrupt cached bytes', bad.read_bytes())
                self.assertEqual(0, self.receipt()['network_requests'])
                self.assertFalse(self.receipt()['accepted'])
        self.assertEqual([], self.server.requests)

    def test_pinned_cached_archive_can_extract_offline(self):
        self.cache.mkdir(); (self.cache / self.aar['name']).write_bytes(self.server.body)
        result = self.prepare(offline=True)
        self.assertTrue(result['accepted'])
        self.assertEqual(0, result['network_requests'])
        self.assertEqual(BODY, (self.cache / self.jar['name']).read_bytes())
        self.assertEqual([], self.server.requests)

    def test_invalid_archive_members_never_publish_a_jar(self):
        cases = [[('wrong.jar', BODY)], [('classes.jar', BODY), ('classes.jar', BODY)],
                 [('classes.jar', BODY + b'extra')], [('classes.jar', b'X' * len(BODY))]]
        for index, members in enumerate(cases):
            with self.subTest(index=index):
                self.cache, self.report = self.work / f'cache-{index}', self.work / f'receipt-{index}.json'
                body = archive(members)
                self.aar.update(bytes=len(body), sha256=digest(body))
                self.cache.mkdir(); (self.cache / self.aar['name']).write_bytes(body)
                with self.assertRaises(ValueError):
                    self.prepare(offline=True)
                self.assertEqual(0, self.receipt()['network_requests'])
                self.assert_no_jar_or_partial()
        self.assertEqual([], self.server.requests)

    def test_offline_missing_dependency_is_a_recorded_failure(self):
        with self.assertRaisesRegex(ValueError, 'missing in offline mode'):
            self.prepare(offline=True)
        self.assertEqual(0, self.receipt()['network_requests'])
        self.assert_no_jar_or_partial()

    def test_existing_evidence_is_not_overwritten(self):
        self.report.write_text('previous evidence\n')
        with self.assertRaisesRegex(ValueError, 'new receipt'):
            self.prepare()
        self.assertEqual('previous evidence\n', self.report.read_text())
        self.assertEqual([], self.server.requests)

    def test_total_process_deadline_stops_a_trickling_body_and_cleans_partial(self):
        self.server.slow = True
        code = ('from pathlib import Path; import sys; sys.path.insert(0, '
                + repr(str(Path(bootstrap.__file__).resolve().parent)) + '); '
                + 'import prepare_dexkit as d; d.AAR=' + repr(self.aar) + '; d.JAR=' + repr(self.jar) + '; '
                + 'd.prepare(Path(' + repr(str(self.cache)) + '),Path(' + repr(str(self.report)) + '),timeout=0.5)')
        result = bootstrap.transport.supervise([sys.executable, '-c', code], self.cache, self.report, 0.5)
        self.assertFalse(result['accepted'])
        self.assertEqual('infrastructure_timeout', result['supervisor_exit'])
        self.assertTrue(result['worker_closed'])
        self.assertEqual(1, len(self.server.requests))
        self.assert_no_jar_or_partial()
        self.assertFalse((self.cache / self.aar['name']).exists())


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    OUT = args.out.resolve(); OUT.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DexKitPreparationControls)
    with (OUT / 'test.log').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = {'accepted': result.wasSuccessful(), 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'synthetic_loopback_fixtures': True, 'real_dexkit_compilation_claimed': False}
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)
    if not result.wasSuccessful():
        print((OUT / 'test.log').read_text())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
