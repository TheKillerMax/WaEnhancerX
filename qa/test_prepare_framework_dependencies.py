#!/usr/bin/env python3
"""Loopback controls for the exact 36-file selector, AAR extraction and cache miss.

Fixture bodies are deliberately synthetic. Canonical JAR execution and the
historical artifact/cache roundtrip have their own separately identified receipts.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
import warnings
import zipfile

import prepare_framework_dependencies as framework

OUT = None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def aar(body, duplicate=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive, warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        archive.writestr(zipfile.ZipInfo('classes.jar'), body)
        if duplicate:
            archive.writestr(zipfile.ZipInfo('classes.jar'), body)
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        responses = self.server.responses.get(self.path, [])
        code, headers, body = responses.pop(0) if responses else (404, {}, b'unexpected URL')
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers.items():
            self.send_header(name, value)
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


class FrameworkPreparationControls(unittest.TestCase):
    def setUp(self):
        self.work = OUT/self._testMethodName; self.work.mkdir()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.requests, self.server.responses, self.server.slow = [], {}, False
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.lock_data = json.loads(framework.LOCK.read_bytes())
        self.archive_bytes, self.bodies = {}, {}
        for index, item in enumerate(self.lock_data['files']):
            body = ('synthetic locked dependency ' + item['name'] + '\n').encode()
            self.bodies[item['name']] = body
            item.update(bytes=len(body), sha256=digest(body),
                        url=f'http://127.0.0.1:{self.server.server_port}/artifact/{index}')
            if 'archive_member' in item:
                body = aar(body)
                item['archive_sha256'] = digest(body)
                self.archive_bytes[digest(body)] = len(body)
            self.server.responses['/artifact/' + str(index)] = [(200, {}, body)]
        self.items = [item for item in self.lock_data['files'] if item['directory'] == 'deps']
        self.archives = [item for item in self.items if 'archive_member' in item]
        self.lock = self.work/'synthetic-lock.json'; self.save_lock()
        self.out, self.report = self.work/'deps', self.work/'receipt.json'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
        (self.work/'http-requests.json').write_text(json.dumps(self.server.requests) + '\n')

    def save_lock(self):
        self.lock.write_text(json.dumps(self.lock_data, indent=2) + '\n')

    def prepare(self, **options):
        return framework.prepare(self.out, self.report, lock=self.lock,
                                 archive_bytes=self.archive_bytes, **options)

    def receipt(self):
        return json.loads(self.report.read_bytes())

    def cache(self, omit=()):
        cache = self.work/'cache'; cache.mkdir()
        for item in self.items:
            if item['name'] not in omit:
                (cache/item['name']).write_bytes(self.bodies[item['name']])
        return cache

    def path(self, item):
        return item['url'].split(str(self.server.server_port), 1)[1]

    def test_cold_graph_fetches_36_exact_urls_and_extracts_both_aars_without_maven(self):
        with mock.patch('subprocess.Popen', side_effect=AssertionError('No Maven or child resolution is permitted')):
            result = self.prepare(timeout=10)
        self.assertTrue(result['accepted']); self.assertEqual(36, result['network_requests'])
        self.assertEqual([self.path(item) for item in self.items], self.server.requests)
        self.assertEqual({item['name'] for item in self.items}, {p.name for p in self.out.iterdir()})
        self.assertIn('nativeruntime-dist-compat-1.0.19.jar', {p.name for p in self.out.iterdir()})
        self.assertEqual(2, sum(row.get('container', {}).get('verified', False) for row in result['files']))
        for item in self.items:
            self.assertEqual(self.bodies[item['name']], (self.out/item['name']).read_bytes())

    def test_warm_graph_is_rehashed_without_http(self):
        self.out.mkdir()
        for item in self.items:
            (self.out/item['name']).write_bytes(self.bodies[item['name']])
        result = self.prepare()
        self.assertTrue(result['accepted']); self.assertEqual([], self.server.requests)
        self.assertEqual(0, result['network_requests'])
        self.assertTrue(all(row['source'] == 'existing_destination' and row['verified'] for row in result['files']))

    def test_verified_cache_stages_all_36_offline(self):
        result = self.prepare(cache=self.cache(), offline=True)
        self.assertTrue(result['accepted']); self.assertEqual([], self.server.requests)
        self.assertEqual(36, len(result['files']))
        self.assertTrue(all(row['source'] == 'verified_cache' and row['verified'] for row in result['files']))

    def test_bad_late_cache_stops_before_fetching_an_earlier_missing_jar(self):
        cache = self.cache(omit=(self.items[0]['name'],))
        (cache/self.items[-1]['name']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=cache)
        self.assertEqual([], self.server.requests); self.assertFalse(self.receipt()['accepted'])

    def test_bad_destination_cannot_fall_back_to_verified_cache(self):
        cache = self.cache(); self.out.mkdir()
        (self.out/self.items[0]['name']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=cache)
        self.assertEqual([], self.server.requests)
        self.assertEqual(b'corrupt', (self.out/self.items[0]['name']).read_bytes())

    def test_missing_dependency_offline_has_no_network_fallback(self):
        with self.assertRaisesRegex(ValueError, 'missing in offline mode'):
            self.prepare(offline=True)
        self.assertEqual([], self.server.requests); self.assertFalse(self.receipt()['accepted'])

    def test_unexpected_cache_file_is_rejected_before_http(self):
        cache = self.cache(); (cache/'extra.jar').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'Unexpected files'):
            self.prepare(cache=cache)
        self.assertEqual([], self.server.requests)

    def test_symlink_input_is_rejected_before_http(self):
        cache = self.cache(); item = self.items[-1]
        (cache/item['name']).unlink()
        (cache/item['name']).symlink_to(cache/self.items[0]['name'])
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            self.prepare(cache=cache)
        self.assertEqual([], self.server.requests)

    def test_wrong_aar_container_is_not_retried_or_published(self):
        item = self.archives[0]; path = self.path(item)
        code, headers, body = self.server.responses[path][0]
        self.server.responses[path] = [(code, headers, b'X'*len(body))]
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=self.cache(omit=(item['name'],)))
        self.assertEqual([path], self.server.requests); self.assertFalse((self.out/item['name']).exists())
        self.assertEqual([], list(self.out.glob('.*')))

    def test_wrong_extracted_jar_is_not_published(self):
        item = self.archives[0]; item['sha256'] = '0'*64; self.save_lock()
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.prepare(cache=self.cache(omit=(item['name'],)))
        self.assertEqual([self.path(item)], self.server.requests)
        self.assertFalse((self.out/item['name']).exists()); self.assertEqual([], list(self.out.glob('.*')))

    def test_duplicate_classes_member_is_rejected(self):
        item = self.archives[0]; body = aar(self.bodies[item['name']], duplicate=True)
        item['archive_sha256'] = digest(body); self.archive_bytes[digest(body)] = len(body); self.save_lock()
        self.server.responses[self.path(item)] = [(200, {}, body)]
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.prepare(cache=self.cache(omit=(item['name'],)))
        self.assertFalse((self.out/item['name']).exists()); self.assertEqual([], list(self.out.glob('.*')))

    def test_unreviewed_container_metadata_is_rejected_before_http(self):
        self.archive_bytes.pop(self.archives[0]['archive_sha256'])
        with self.assertRaisesRegex(ValueError, 'reviewed container metadata'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_long_retry_after_is_retained_without_early_retry(self):
        item = self.items[0]; path = self.path(item)
        self.server.responses[path] = [(429, {'Retry-After': '39363'}, b'rate limited')]
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            self.prepare(timeout=10)
        self.assertEqual([path], self.server.requests)
        attempt = self.receipt()['files'][0]['attempts'][0]
        self.assertEqual(39363, attempt['retry_after_seconds'])
        self.assertEqual('retry_deferred_beyond_budget', attempt['status'])

    def test_transient_response_uses_the_existing_bounded_transport(self):
        item = self.items[0]; path = self.path(item)
        self.server.responses[path].insert(0, (503, {}, b'transient'))
        result = self.prepare(timeout=10)
        self.assertTrue(result['accepted']); self.assertEqual(37, result['network_requests'])
        self.assertEqual([503, 200], [attempt['http_status'] for attempt in result['files'][0]['attempts']])

    def test_missing_real_native_runtime_name_invalidates_the_graph(self):
        self.lock_data['files'] = [item for item in self.lock_data['files']
                                   if item['name'] != 'nativeruntime-dist-compat-1.0.19.jar']
        self.save_lock()
        with self.assertRaisesRegex(ValueError, 'complete framework'):
            self.prepare()
        self.assertEqual([], self.server.requests)

    def test_supervisor_stops_slow_aar_and_removes_both_staging_layers(self):
        item = self.archives[0]; cache = self.cache(omit=(item['name'],)); self.server.slow = True
        module = str(Path(framework.__file__).resolve().parent)
        code = ('from pathlib import Path; import sys; sys.path.insert(0, ' + repr(module) + '); '
                'from prepare_framework_dependencies import prepare; '
                f'prepare(Path({str(self.out)!r}), Path({str(self.report)!r}), '
                f'cache=Path({str(cache)!r}), lock=Path({str(self.lock)!r}), '
                f'archive_bytes={self.archive_bytes!r}, timeout=60)')
        start = time.monotonic()
        result = framework.supervise([sys.executable, '-c', code], self.out, self.report, timeout=0.4, cache=cache)
        self.assertLess(time.monotonic()-start, 6.0); self.assertFalse(result['accepted'])
        self.assertEqual('infrastructure_timeout', result['supervisor_exit']); self.assertTrue(result['worker_closed'])
        self.assertEqual([self.path(item)], self.server.requests)
        self.assertFalse((self.out/item['name']).exists()); self.assertEqual([], list(self.out.glob('.*')))

    def test_evidence_inside_destination_or_cache_is_rejected_without_writes(self):
        controls = []

        def snapshot(root):
            return {path.relative_to(root).as_posix(): (
                {'symlink': str(path.readlink())} if path.is_symlink() else
                {'directory': True} if path.is_dir() else {'sha256': digest(path.read_bytes())})
                for path in root.rglob('*')}

        for entry in ('prepare', 'supervise', 'main'):
            for owner in ('out', 'cache'):
                for kind in ('report', 'worker_log_alias', 'pending_alias'):
                    with self.subTest(entry=entry, owner=owner, kind=kind):
                        root = self.work/(entry+'-'+owner+'-'+kind); root.mkdir()
                        out, cache = root/'deps', root/'cache'; cache.mkdir()
                        for item in self.items:
                            (cache/item['name']).write_bytes(self.bodies[item['name']])
                        artifact_root = out if owner == 'out' else cache
                        report = artifact_root/'receipt.json'
                        if kind != 'report':
                            evidence = root/'evidence'; evidence.mkdir(); report = evidence/'receipt.json'
                            sidecar = (report.with_suffix('.worker.log') if kind == 'worker_log_alias'
                                       else report.with_suffix(report.suffix+'.pending'))
                            sidecar.symlink_to(artifact_root/'unwanted-evidence')
                        before = snapshot(root)
                        message = 'Evidence paths must remain outside framework destination/cache'
                        if entry == 'prepare':
                            with self.assertRaisesRegex(ValueError, message):
                                framework.prepare(out, report, cache=cache, offline=True, lock=self.lock)
                        elif entry == 'supervise':
                            command = [sys.executable, '-c', 'raise SystemExit("worker must not start")']
                            with mock.patch.object(framework.transport, 'supervise',
                                    side_effect=AssertionError('The supervisor must reject before launching or writing')):
                                with self.assertRaisesRegex(ValueError, message):
                                    framework.supervise(command, out, report, 10, cache=cache)
                        else:
                            result = subprocess.run([sys.executable, str(Path(framework.__file__).resolve()),
                                '--offline', '--out', str(out), '--cache', str(cache), '--report', str(report)],
                                capture_output=True, text=True, timeout=10)
                            self.assertEqual(1, result.returncode)
                            self.assertIn(message, result.stdout+result.stderr)
                        self.assertEqual(before, snapshot(root))
                        self.assertFalse(out.exists())
                        self.assertEqual(36, len(list(cache.iterdir())))
                        controls.append({'entry': entry, 'owner': owner, 'kind': kind,
                                         'rejected': True, 'filesystem_unchanged': True, 'http_requests': 0})
        self.assertEqual([], self.server.requests)
        (self.work/'evidence-path-controls.json').write_text(json.dumps({
            'accepted': True, 'tests': len(controls), 'controls': controls}, indent=2)+'\n')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); OUT = args.out.resolve(); OUT.mkdir(parents=True, exist_ok=False)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FrameworkPreparationControls))
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'accepted': result.wasSuccessful(),
              'scope': 'Synthetic loopback graph/AAR/cache controls; not Android execution',
              'driver_sha256': framework.sha(Path(__file__)),
              'preparer_sha256': framework.sha(Path(framework.__file__)),
              'transport_sha256': framework.sha(Path(framework.transport.__file__))}
    (OUT/'result.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 17 else 1)


if __name__ == '__main__':
    main()
