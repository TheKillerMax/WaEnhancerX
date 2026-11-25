#!/usr/bin/env python3
"""Host contract controls for legacy and major/minor Android version lookup."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import android_emulator_lab_pilot as pilot


class GuestVersionControls(unittest.TestCase):
    def test_legacy_never_queries_unsupported_property(self):
        for api in (24, 25, 26, 30, 33, 34, 35):
            with self.subTest(api=api), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                with patch.object(pilot, 'invoke', side_effect=RuntimeError('legacy getprop exits255')) as call:
                    value = pilot.read_full_sdk_property(out, Path('/owned/adb'), {}, api)
                self.assertEqual(value, '')
                call.assert_not_called()
                policy = json.loads((out / 'guest-sdk-full-policy.json').read_bytes())
                self.assertIs(policy['requested'], False)
                observed = pilot.guest_version_identity({'sdk': str(api), 'sdk_full_property': value},
                                                       {'api': api, 'minor': 0})
                self.assertIs(observed['minor_verified'], False)
                self.assertIsNone(observed['sdk_int_full_from_property'])

    def test_modern_property_is_read_and_minor_identity_is_checked(self):
        for api, minor, text in ((36, 0, '36.0'), (36, 1, '36.1'), (37, 2, '37.2')):
            with self.subTest(api=api, minor=minor), tempfile.TemporaryDirectory() as tmp:
                with patch.object(pilot, 'invoke', return_value=({}, text + '\n')) as call:
                    value = pilot.read_full_sdk_property(Path(tmp), Path('/owned/adb'), {'OWNED': 'yes'}, api)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[2], ['/owned/adb', '-s', 'emulator-5580', 'shell',
                                                        'getprop', 'ro.build.version.sdk_full'])
                self.assertEqual(call.call_args.args[3], {'OWNED': 'yes'})
                self.assertNotEqual(call.call_args.kwargs.get('required'), False)
                observed = pilot.guest_version_identity({'sdk': str(api), 'sdk_full_property': value},
                                                       {'api': api, 'minor': minor})
                self.assertEqual(observed['sdk_int_full_from_property'], api * 100000 + minor)
                self.assertIs(observed['minor_verified'], True)

    def test_modern_transport_failure_is_not_reclassified_as_missing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pilot, 'invoke', side_effect=RuntimeError('transport255')):
                with self.assertRaisesRegex(RuntimeError, 'transport255'):
                    pilot.read_full_sdk_property(Path(tmp), Path('/owned/adb'), {}, 36)
            self.assertIs(json.loads((Path(tmp) / 'guest-sdk-full-policy.json').read_bytes())['requested'], True)

    def test_malformed_missing_or_wrong_modern_version_still_blocks(self):
        for raw in ('', '35.1', '36.0', '36.2', '36.-1', '36.1.0', '36.100000', 'NaN'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                pilot.guest_version_identity({'sdk': '36', 'sdk_full_property': raw}, {'api': 36, 'minor': 1})

    def test_major_api_and_legacy_minor_mismatch_still_block(self):
        for guest, expected in (({'sdk': '25'}, {'api': 24, 'minor': 0}),
                                 ({'sdk': '24'}, {'api': 24, 'minor': 1}),
                                 ({'sdk': '35', 'sdk_full_property': '36.1'}, {'api': 36, 'minor': 1})):
            with self.subTest(guest=guest), self.assertRaises(RuntimeError):
                pilot.guest_version_identity(guest, expected)

    def test_policy_requires_a_reviewed_integer_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            for api in (True, 24.0, '24', 23, 38):
                with self.subTest(api=api), self.assertRaises(RuntimeError):
                    pilot.read_full_sdk_property(Path(tmp), Path('/owned/adb'), {}, api)


if __name__ == '__main__':
    unittest.main()
