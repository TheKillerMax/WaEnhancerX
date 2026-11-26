#!/usr/bin/env python3
"""Check Renderer input composition with explicitly synthetic 39-file/SDK bytes.

Loopback HTTP exercises only the new SDK36 selection. It is not Android evidence;
the unchanged Renderer and mutation runners are qualified separately on real JARs.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
import urllib.request

import prepare_presence_framework as bootstrap
from framework_dependency_bundle import metadata

OUT = None
BODY = b'Explicit synthetic SDK36 transport fixture\n'
ORIGIN = {'run_id': '9000000000000000001', 'run_attempt': '1', 'head_sha': '0' * 40}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        status, headers, body = self.server.responses.pop(0) if self.server.responses else (200, {}, BODY)
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            if self.server.slow:
                for value in body:
                    self.wfile.write(bytes([value])); self.wfile.flush(); time.sleep(0.05)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


class PresenceInputControls(unittest.TestCase):
    def setUp(self):
        self.work = OUT / self._testMethodName
        self.work.mkdir()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.requests, self.server.responses, self.server.slow = [], [], False
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.requested_urls = []
        self.bundle = self.work / 'bundle'
        self.bundle.mkdir()
        lock = json.loads(bootstrap.LOCK.read_bytes())
        for item in lock['files']:
            data = ('explicit synthetic framework input: ' + item['directory'] + '/' + item['name']).encode()
            item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            target = self.bundle / item['directory'] / item['name']
            target.parent.mkdir(exist_ok=True); target.write_bytes(data)
        self.lock = self.work / 'synthetic-framework-lock.json'
        self.lock.write_text(json.dumps(lock, indent=2) + '\n')
        (self.bundle / 'bundle.json').write_text(json.dumps(metadata(self.lock, lock['files'], ORIGIN), indent=2) + '\n')
        selector = json.loads(bootstrap.SELECTION.read_bytes())
        selector['framework_lock_sha256'] = bootstrap.sha(self.lock)
        for item in selector['files'][:2]:
            original = next(row for row in lock['files'] if row['name'] == item['name'])
            item.update(bytes=original['bytes'], sha256=original['sha256'])
        selector['files'][2].update(bytes=len(BODY), sha256=hashlib.sha256(BODY).hexdigest())
        self.selector = self.work / 'synthetic-selection.json'
        self.selector.write_text(json.dumps(selector, indent=2) + '\n')
        self.items = selector['files']
        self.output, self.report = self.work / 'sdk-view', self.work / 'receipt.json'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
        (self.work / 'http-requests.json').write_text(json.dumps({
            'loopback_requests': self.server.requests, 'selected_urls': self.requested_urls}, indent=2) + '\n')

    def opener(self, request, *, timeout):
        self.requested_urls.append(request.full_url)
        self.assertEqual(self.items[2]['url'], request.full_url)
        return urllib.request.urlopen('http://127.0.0.1:' + str(self.server.server_port) + '/sdk36', timeout=timeout)

    def prepare(self, **kwargs):
        return bootstrap.prepare(self.bundle, self.output, self.report, kwargs.pop('origin', ORIGIN),
                                 selector=self.selector, lock=self.lock, opener=kwargs.pop('opener', self.opener), **kwargs)

    def receipt(self):
        return json.loads(self.report.read_bytes())

    def test_cold_path_downloads_only_sdk36_and_rechecks_the_whole_bundle(self):
        result = self.prepare(timeout=10)
        self.assertTrue(result['accepted'])
        self.assertEqual(1, result['network_requests'])
        self.assertEqual(['/sdk36'], self.server.requests)
        self.assertEqual([28, 34, 36], [item['sdk'] for item in result['files']])
        self.assertEqual(39, result['bundle_before']['verified_files'])
        self.assertEqual(result['bundle_before'], result['bundle_after'])
        self.assertEqual({item['name'] for item in self.items}, {path.name for path in self.output.iterdir()})

    def test_restored_sdk36_is_rehashed_and_never_requested(self):
        self.output.mkdir(); (self.output / self.items[2]['name']).write_bytes(BODY)
        result = self.prepare(offline=True)
        self.assertTrue(result['accepted']); self.assertEqual(0, result['network_requests'])
        self.assertEqual([], self.server.requests)
        self.assertEqual('verified_existing_destination', result['files'][2]['source'])

    def test_offline_missing_sdk36_stops_before_network_or_staging(self):
        with self.assertRaisesRegex(ValueError, 'missing in offline mode'):
            self.prepare(offline=True)
        self.assertEqual([], self.server.requests); self.assertFalse(self.output.exists())

    def test_bad_existing_sdk_is_rejected_before_requesting_missing_sdk36(self):
        self.output.mkdir(); (self.output / self.items[0]['name']).write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare()
        self.assertEqual([], self.server.requests)
        self.assertFalse(self.receipt()['accepted'])

    def test_corrupt_restored_sdk36_is_not_replaced_by_a_network_fallback(self):
        self.output.mkdir(); target = self.output / self.items[2]['name']; target.write_bytes(b'bad cache')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare()
        self.assertEqual(b'bad cache', target.read_bytes()); self.assertEqual([], self.server.requests)

    def test_wrong_run_attempt_or_head_is_rejected_before_any_download(self):
        for key, value in [('run_id', '2'), ('run_attempt', '2'), ('head_sha', '1' * 40)]:
            with self.subTest(key=key):
                self.report = self.work / (key + '.json')
                with self.assertRaisesRegex(ValueError, 'origin mismatch'):
                    self.prepare(origin={**ORIGIN, key: value})
                self.assertFalse(self.receipt()['accepted'])
        self.assertEqual([], self.server.requests)

    def test_receipt_inside_input_bundle_cannot_mutate_any_input(self):
        before = {path.relative_to(self.bundle).as_posix(): bootstrap.sha(path)
                  for path in self.bundle.rglob('*') if path.is_file()}
        for relative in ('receipt.json', 'nested/receipt.json'):
            with self.subTest(relative=relative):
                self.report = self.bundle / relative
                with self.assertRaisesRegex(ValueError, 'outside the immutable input bundle'):
                    self.prepare()
                self.assertFalse(self.report.exists())
                self.assertFalse(self.output.exists())
                self.assertEqual(before, {path.relative_to(self.bundle).as_posix(): bootstrap.sha(path)
                                          for path in self.bundle.rglob('*') if path.is_file()})
        self.assertEqual([], self.server.requests)

    def test_cli_rejects_input_or_output_receipts_before_supervisor_writes(self):
        before = {path.relative_to(self.bundle).as_posix(): bootstrap.sha(path)
                  for path in self.bundle.rglob('*') if path.is_file()}
        reports = [self.bundle / 'receipt.json', self.bundle / 'nested/receipt.json', self.output,
                   self.output / 'receipt.json', self.work / 'absent/../bundle/receipt.json']
        for report in reports:
            with self.subTest(report=str(report)):
                command = [sys.executable, str(Path(bootstrap.__file__)), '--bundle', str(self.bundle),
                           '--out', str(self.output), '--report', str(report), '--run-id', ORIGIN['run_id'],
                           '--run-attempt', ORIGIN['run_attempt'], '--head-sha', ORIGIN['head_sha']]
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(0, result.returncode)
                self.assertIn('outside the immutable input bundle', result.stdout + result.stderr)
                self.assertFalse(report.exists()); self.assertFalse(report.with_suffix('.worker.log').exists())
                self.assertFalse(self.output.exists()); self.assertFalse((self.work / 'absent').exists())
                self.assertEqual(before, {path.relative_to(self.bundle).as_posix(): bootstrap.sha(path)
                                          for path in self.bundle.rglob('*') if path.is_file()})
        self.assertEqual([], self.server.requests)

    def test_all_evidence_paths_are_rejected_before_api_supervisor_or_cli_writes(self):
        def snapshot():
            return {path.relative_to(self.work).as_posix(): (
                {'symlink': str(path.readlink())} if path.is_symlink() else
                {'directory': True} if path.is_dir() else {'sha256': bootstrap.sha(path)})
                for path in self.work.rglob('*')}

        controls = []
        for entry in ('prepare', 'supervise', 'main'):
            for owner in ('bundle', 'out'):
                for kind in ('report', 'worker_log_alias', 'pending_alias'):
                    with self.subTest(entry=entry, owner=owner, kind=kind):
                        case = self.work / (entry + '-' + owner + '-' + kind); case.mkdir()
                        out = case / 'sdk-view'
                        artifact_root = self.bundle if owner == 'bundle' else out
                        report = artifact_root / 'receipt.json'
                        if kind != 'report':
                            evidence = case / 'evidence'; evidence.mkdir(); report = evidence / 'receipt.json'
                            sidecar = (report.with_suffix('.worker.log') if kind == 'worker_log_alias'
                                       else report.with_suffix(report.suffix + '.pending'))
                            sidecar.symlink_to(artifact_root / 'unwanted-evidence')
                        before = snapshot()
                        message = 'outside the immutable input bundle'
                        if entry == 'prepare':
                            with self.assertRaisesRegex(ValueError, message):
                                bootstrap.prepare(self.bundle, out, report, ORIGIN,
                                                  selector=self.selector, lock=self.lock, opener=self.opener)
                        elif entry == 'supervise':
                            with self.assertRaisesRegex(ValueError, message):
                                bootstrap.supervise([sys.executable, '-c', 'raise SystemExit("must not start")'],
                                                    self.bundle, out, report, 10)
                        else:
                            result = subprocess.run([sys.executable, str(Path(bootstrap.__file__)),
                                '--bundle', str(self.bundle), '--out', str(out), '--report', str(report),
                                '--run-id', ORIGIN['run_id'], '--run-attempt', ORIGIN['run_attempt'],
                                '--head-sha', ORIGIN['head_sha']], capture_output=True, text=True, timeout=10)
                            self.assertEqual(1, result.returncode)
                            self.assertIn(message, result.stdout + result.stderr)
                        self.assertEqual(before, snapshot()); self.assertFalse(out.exists())
                        controls.append({'entry': entry, 'owner': owner, 'kind': kind, 'rejected': True,
                                         'filesystem_unchanged': True, 'http_requests': 0})
        self.assertEqual([], self.server.requests)
        (self.work / 'evidence-path-controls.json').write_text(json.dumps({
            'accepted': True, 'subcases': len(controls), 'controls': controls}, indent=2) + '\n')

    def test_changed_runtime_jar_blocks_the_sdk36_request(self):
        next((self.bundle / 'deps').glob('*.jar')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_unexpected_destination_entry_is_not_ignored(self):
        self.output.mkdir(); (self.output / 'unreviewed.jar').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'Unexpected files'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_symlink_sdk_is_refused_even_when_it_points_to_correct_bytes(self):
        self.output.mkdir(); target = self.work / 'real-sdk36'; target.write_bytes(BODY)
        (self.output / self.items[2]['name']).symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_incompatible_api_or_framework_lock_is_rejected(self):
        original = json.loads(self.selector.read_bytes())
        for key, value in [('sdk_levels', [24, 28, 34]), ('framework_lock_sha256', '0' * 64)]:
            with self.subTest(key=key):
                self.report = self.work / (key + '.json')
                self.selector.write_text(json.dumps({**original, key: value}))
                with self.assertRaisesRegex(ValueError, 'Unsupported'):
                    self.prepare()
        self.assertEqual([], self.server.requests)

    def test_sdk36_cannot_redirect_the_selected_coordinate_or_url(self):
        selector = json.loads(self.selector.read_bytes()); selector['files'][2]['url'] += '?unreviewed=1'
        self.selector.write_text(json.dumps(selector))
        with self.assertRaisesRegex(ValueError, 'exact reviewed'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_wrong_sdk36_body_is_neither_retried_nor_published(self):
        self.server.responses = [(200, {}, b'X' * len(BODY))]
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk36'], self.server.requests)
        self.assertFalse((self.output / self.items[2]['name']).exists())
        self.assertEqual([], list(self.output.glob('.sdk-download-*')))

    def test_retry_after_beyond_budget_is_not_retried_early(self):
        self.server.responses = [(429, {'Retry-After': '79681'}, b'rate limited')]
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            self.prepare(timeout=10)
        self.assertEqual(['/sdk36'], self.server.requests)
        self.assertEqual('retry_deferred_beyond_budget', self.receipt()['files'][2]['attempts'][0]['status'])

    def test_changed_bundle_during_sdk_download_cannot_be_accepted(self):
        def changed(request, *, timeout):
            next((self.bundle / 'deps').glob('*.jar')).write_bytes(b'changed during transport')
            return self.opener(request, timeout=timeout)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(opener=changed)
        self.assertFalse(self.receipt()['accepted'])

    def test_changed_selected_sdk_during_download_is_rechecked(self):
        def changed(request, *, timeout):
            (self.output / self.items[0]['name']).write_bytes(b'changed selected SDK')
            return self.opener(request, timeout=timeout)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(opener=changed)
        self.assertFalse(self.receipt()['accepted'])

    def test_changed_selection_during_download_cannot_be_accepted(self):
        def changed(request, *, timeout):
            self.selector.write_bytes(self.selector.read_bytes() + b'\n')
            return self.opener(request, timeout=timeout)
        with self.assertRaisesRegex(ValueError, 'changed during execution'):
            self.prepare(opener=changed)
        self.assertFalse(self.receipt()['accepted'])

    def test_total_worker_deadline_cleans_the_incomplete_sdk36(self):
        self.server.slow = True
        code = ('from pathlib import Path; import sys, urllib.request; sys.path.insert(0, '
                + repr(str(bootstrap.HERE)) + '); import prepare_presence_framework as p; '
                + 'opener=lambda request, timeout: urllib.request.urlopen('
                + repr('http://127.0.0.1:' + str(self.server.server_port) + '/sdk36') + ', timeout=timeout); '
                + f'p.prepare(Path({str(self.bundle)!r}), Path({str(self.output)!r}), Path({str(self.report)!r}), '
                + repr(ORIGIN) + f', selector=Path({str(self.selector)!r}), lock=Path({str(self.lock)!r}), opener=opener, timeout=60)')
        start = time.monotonic()
        result = bootstrap.supervise([sys.executable, '-c', code], self.bundle, self.output, self.report, timeout=0.5)
        self.assertLess(time.monotonic() - start, 6)
        self.assertFalse(result['accepted']); self.assertTrue(result['worker_closed'])
        self.assertEqual('infrastructure_timeout', result['supervisor_exit'])
        self.assertEqual(['/sdk36'], self.server.requests)
        self.assertFalse((self.output / self.items[2]['name']).exists())
        self.assertEqual([], list(self.output.glob('.sdk-download-*')))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    OUT = args.out.absolute(); OUT.mkdir(parents=True, exist_ok=False)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PresenceInputControls))
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'accepted': result.wasSuccessful(),
              'scope': 'Explicit synthetic graph and loopback HTTP controls; not Android execution',
              'driver_sha256': bootstrap.sha(Path(__file__)), 'source_sha256': bootstrap.source_pins()}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 20 else 1)


if __name__ == '__main__':
    main()
