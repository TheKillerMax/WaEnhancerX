#!/usr/bin/env python3
"""Host protocol controls only: no Android, network or native build."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import build_presence_art_lab as build
import android_presence_art_lab as art


class Response(io.BytesIO):
    status = 200


def pin_for(data):
    return {'name': 'host-control.jar', 'url': 'https://repo.maven.apache.org/maven2/host-control.jar',
            'bytes': len(data), **{name: hashlib.new(name, data).hexdigest()
                                  for name in ('sha1', 'sha256', 'sha512')}}


class ArtLabControls(unittest.TestCase):
    def test_all_pinned_jar_hashes_and_length(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.jar'; data = b'HOST ONLY, NOT A JAR'; path.write_bytes(data)
            pin = pin_for(data); build.verify_jar(path, pin)
            for key in ('sha1', 'sha256', 'sha512', 'bytes'):
                bad = dict(pin); bad[key] = pin[key] + 1 if key == 'bytes' else '0' * len(pin[key])
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    build.verify_jar(path, bad)

    def test_single_successful_request_and_no_existing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.jar'; data = b'HOST ONLY'; calls = []
            def opener(request, timeout):
                calls.append((request.full_url, timeout)); return Response(data)
            receipt = {}; build.acquire(pin_for(data), path, receipt, opener)
            self.assertEqual(len(calls), 1); self.assertEqual(receipt['status'], 'VERIFIED')
            with self.assertRaises(RuntimeError):
                build.acquire(pin_for(data), path, {}, opener)
            self.assertEqual(len(calls), 1)

    def test_http429_stops_after_one_request(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.jar'; calls = []
            def opener(request, timeout):
                calls.append(request.full_url)
                raise urllib.error.HTTPError(request.full_url, 429, 'Too Many Requests',
                                             {'Retry-After': '60'}, None)
            receipt = {}
            with self.assertRaises(RuntimeError):
                build.acquire(pin_for(b'X'), path, receipt, opener)
            self.assertEqual(len(calls), 1); self.assertEqual(receipt['code'], 429)
            self.assertFalse(path.exists()); self.assertFalse(path.with_suffix('.jar.partial').exists())

    def test_source_pin_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'source').write_bytes(b'original')
            pins = {'source': build.digest(root / 'source')}
            build.verify_files(root, pins); (root / 'source').write_bytes(b'changed')
            with self.assertRaises(RuntimeError): build.verify_files(root, pins)

    def test_art_receipt_requires_finish_cleanup_cases_and_all_pngs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'device-result.json').write_text('{}\n')
            for index in range(7):
                (root / ('phase_' + str(index) + '.png')).write_bytes(b'\x89PNG\r\n\x1a\nHOST CONTROL')
            receipt = {'status': 'PASS', 'failure': None, 'api': 24, 'serial': 'emulator-5580',
                       'apk_sha256': 'a' * 64, 'installed_apk_sha256': 'a' * 64,
                       'initially_absent': True, 'cleanup': {'status': 'PASS', 'verified_absent': True},
                       'instrumentation_finish_verified': True, 'all_seven_png_phases_present': True,
                       'device_counts': {'tests': 4, 'passed': 4, 'failures': 0, 'errors': 0, 'skipped': 0},
                       'device_result_sha256': build.digest(root / 'device-result.json'),
                       'png_sha256': {p.name: build.digest(p) for p in root.glob('*.png')}}
            art.validate_receipt(receipt, 24, 'a' * 64, root)
            mutations = [('instrumentation_finish_verified', False), ('all_seven_png_phases_present', False),
                         ('initially_absent', False), ('installed_apk_sha256', 'b' * 64),
                         ('serial', 'physical-phone'), ('cleanup', {'status': 'PASS', 'verified_absent': False}),
                         ('device_counts', {'tests': 3, 'passed': 3, 'failures': 0, 'errors': 0, 'skipped': 1}),
                         ('device_result_sha256', 'c' * 64)]
            for key, value in mutations:
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    bad = copy.deepcopy(receipt); bad[key] = value
                    art.validate_receipt(bad, 24, 'a' * 64, root)
            (root / 'phase_0.png').write_bytes(b'CHANGED')
            with self.assertRaises(RuntimeError): art.validate_receipt(receipt, 24, 'a' * 64, root)

    def test_artifact_requires_same_workflow_lock_and_independent_digest(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_SHA': 'd' * 40}):
            root = Path(temp); apk = root / 'presence-art-positive.apk'
            apk.write_bytes(b'HOST PROTOCOL ONLY; NOT AN APK'); lock = build.checked_lock()
            receipt = {'schema': 'WAEX_ART_BUILD_V1', 'status': 'PASS_BUILD_ONLY',
                       'source_revision': build.SOURCE, 'probe_revision': lock['probe_revision'],
                       'workflow_commit': 'd' * 40, 'lock_sha256': build.digest(build.LOCK),
                       'renderer_harness_sha256': lock['renderer_harness_sha256'],
                       'package': build.PACKAGE, 'expected_tests': 4, 'min_sdk': 24, 'target_sdk': 28,
                       'installed': False, 'art_execution': 'NOT_RUN', 'ephemeral_key_absent': True,
                       'apk': {'bytes': apk.stat().st_size, 'sha256': build.digest(apk)}}
            manifest = root / 'artifact-manifest.json'; build.save(manifest, receipt)
            art.verify_artifact(root, build.digest(apk))
            with self.assertRaises(RuntimeError): art.verify_artifact(root, '0' * 64)
            for key, value in [('workflow_commit', 'e' * 40), ('lock_sha256', 'f' * 64),
                               ('ephemeral_key_absent', False), ('source_revision', '0' * 40),
                               ('expected_tests', 3), ('installed', True)]:
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    bad = copy.deepcopy(receipt); bad[key] = value; build.save(manifest, bad)
                    art.verify_artifact(root, build.digest(apk))


if __name__ == '__main__':
    unittest.main(verbosity=2)
