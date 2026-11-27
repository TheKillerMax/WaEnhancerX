#!/usr/bin/env python3
"""Exercise real loopback HTTP failures and fail-closed SDK cache behavior.

Transport fixtures use small synthetic bodies. A separate canonical-lock run
verifies the real API24/28/34 artifacts; these controls do not claim to be SDKs.
"""
import argparse
import datetime
from email.utils import format_datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import sys
import time
import unittest

import prepare_robolectric_sdks as bootstrap

BODY = b'locked synthetic SDK transport body\n'
OUT = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        sequence = self.server.responses.get(self.path, [])
        code, headers, data = sequence.pop(0) if sequence else (200, {}, BODY)
        self.send_response(code)
        self.send_header('Content-Length', str(len(data)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            if getattr(self.server, 'slow', False):
                for byte in data:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.05)
            else:
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The deliberate deadline control closes its client first.

    def log_message(self, *_):
        pass


class SdkBootstrapControls(unittest.TestCase):
    def setUp(self):
        self.work = OUT/self._testMethodName
        self.work.mkdir()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.requests, self.server.responses = [], {}
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        lock = json.loads(bootstrap.LOCK.read_bytes())
        self.items = [row for row in lock['files'] if row['directory'] == 'sdk-jars']
        for index, row in enumerate(self.items):
            row.update(bytes=len(BODY), sha256=hashlib.sha256(BODY).hexdigest(),
                       url=f'http://127.0.0.1:{self.server.server_port}/sdk/{index}')
        self.lock = self.work/'synthetic-lock.json'
        self.lock.write_text(json.dumps(lock, indent=2)+'\n')
        self.output, self.report = self.work/'sdks', self.work/'receipt.json'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        (self.work/'http-requests.json').write_text(json.dumps(self.server.requests)+'\n')

    def prepare(self, **kwargs):
        return bootstrap.prepare(self.output, self.report, lock=self.lock, **kwargs)

    def receipt(self):
        return json.loads(self.report.read_bytes())

    def test_429_retries_once_then_verifies_all_three(self):
        self.server.responses['/sdk/0'] = [(429, {'Retry-After': '0'}, b'rate limited')]
        result = self.prepare(timeout=10)
        self.assertTrue(result['accepted'])
        self.assertEqual(4, result['network_requests'])
        self.assertEqual([429, 200], [row['http_status'] for row in result['files'][0]['attempts']])
        self.assertTrue(all(row['verified'] for row in result['files']))

    def test_503_is_a_bounded_transport_retry(self):
        self.server.responses['/sdk/0'] = [(503, {}, b'temporary')]
        result = self.prepare(timeout=10)
        self.assertEqual(4, result['network_requests'])
        self.assertEqual(1.0, result['files'][0]['attempts'][0]['wait_seconds'])

    def test_404_is_not_retried(self):
        self.server.responses['/sdk/0'] = [(404, {}, b'missing')]
        with self.assertRaises(RuntimeError):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertFalse(self.receipt()['files'][0]['attempts'][0]['retryable'])

    def test_long_retry_after_does_not_retry_early(self):
        self.server.responses['/sdk/0'] = [(429, {'Retry-After': '39363'}, b'rate limited')]
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        attempt = self.receipt()['files'][0]['attempts'][0]
        self.assertEqual(39363, attempt['retry_after_seconds'])
        self.assertEqual('retry_deferred_beyond_budget', attempt['status'])

    def test_http_date_retry_after_is_respected(self):
        when = format_datetime(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1), usegmt=True)
        self.server.responses['/sdk/0'] = [(429, {'Retry-After': when}, b'rate limited')]
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertGreater(self.receipt()['files'][0]['attempts'][0]['retry_after_seconds'], 3500)

    def test_malformed_retry_after_does_not_guess_an_earlier_time(self):
        self.server.responses['/sdk/0'] = [(429, {'Retry-After': 'not-a-date'}, b'rate limited')]
        with self.assertRaises(RuntimeError):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertFalse(self.receipt()['files'][0]['attempts'][0]['retryable'])

    def test_download_hash_mismatch_is_not_retried_or_published(self):
        self.server.responses['/sdk/0'] = [(200, {}, b'X'*len(BODY))]
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertEqual([], list(self.output.iterdir()))
        self.assertFalse(self.receipt()['accepted'])

    def test_oversize_response_is_not_published(self):
        self.server.responses['/sdk/0'] = [(200, {}, BODY+b'extra')]
        with self.assertRaisesRegex(ValueError, 'pinned byte count'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertEqual([], list(self.output.iterdir()))

    def test_bad_cache_fails_before_fetching_an_earlier_missing_file(self):
        cache = self.work/'cache'; cache.mkdir()
        (cache/self.items[2]['name']).write_bytes(b'X'*len(BODY))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=cache, timeout=10)
        self.assertEqual([], self.server.requests)
        self.assertEqual(0, self.receipt()['network_requests'])

    def test_bad_destination_does_not_fall_back_to_a_good_cache(self):
        cache = self.work/'cache'; cache.mkdir(); self.output.mkdir()
        for item in self.items:
            (cache/item['name']).write_bytes(BODY)
        (self.output/self.items[0]['name']).write_bytes(b'X'*len(BODY))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=cache, timeout=10)
        self.assertEqual([], self.server.requests)
        self.assertEqual(b'X'*len(BODY), (self.output/self.items[0]['name']).read_bytes())

    def test_verified_cache_is_reused_with_no_requests(self):
        cache = self.work/'cache'; cache.mkdir()
        for item in self.items:
            (cache/item['name']).write_bytes(BODY)
        result = self.prepare(cache=cache, offline=True)
        self.assertTrue(result['accepted'])
        self.assertEqual(0, result['network_requests'])
        self.assertEqual([], self.server.requests)
        for item in self.items:
            self.assertEqual(BODY, (self.output/item['name']).read_bytes())

    def test_offline_missing_sdk_never_falls_back_to_network(self):
        with self.assertRaisesRegex(ValueError, 'missing in offline mode'):
            self.prepare(offline=True)
        self.assertEqual([], self.server.requests)
        self.assertFalse(self.receipt()['accepted'])

    def test_total_worker_deadline_stops_a_continuously_trickling_body(self):
        self.server.slow = True
        module = str(Path(bootstrap.__file__).resolve().parent)
        code = ('from pathlib import Path; import sys; sys.path.insert(0, '+repr(module)+'); '
                'from prepare_robolectric_sdks import prepare; '
                f'prepare(Path({str(self.output)!r}), Path({str(self.report)!r}), '
                f'lock=Path({str(self.lock)!r}), timeout=60)')
        started = time.monotonic()
        result = bootstrap.supervise([sys.executable, '-c', code], self.output, self.report, timeout=0.4)
        self.assertLess(time.monotonic()-started, 6.0)
        self.assertFalse(result['accepted'])
        self.assertEqual('infrastructure_timeout', result['supervisor_exit'])
        self.assertTrue(result['worker_closed'])
        self.assertEqual(['/sdk/0'], self.server.requests)
        self.assertEqual([], list(self.output.glob('*.jar')))
        self.assertEqual([], list(self.output.glob('.sdk-download-*')))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    OUT = args.out.resolve(); OUT.mkdir(parents=True, exist_ok=False)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SdkBootstrapControls))
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'accepted': result.wasSuccessful(),
              'scope': 'Synthetic loopback HTTP and cache integrity controls; not Android execution',
              'driver_sha256': bootstrap.sha(Path(__file__)),
              'resolver_sha256': bootstrap.sha(Path(bootstrap.__file__))}
    (OUT/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 13 else 1)


if __name__ == '__main__':
    main()
