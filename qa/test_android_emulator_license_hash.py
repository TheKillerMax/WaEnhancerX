#!/usr/bin/env python3
"""Offline regressions for SDK license identity; never records acceptance."""
import hashlib
import unittest
import xml.etree.ElementTree as ET

import android_emulator_lab_preflight as lab


class LicenseHashTests(unittest.TestCase):
    def test_matches_official_sdk12_adapter_oracles(self):
        # Observed from TrimStringAdapter in the official Linux 12.0 archive,
        # tools.repository.jar SHA256 0f1778a98a79fb6f3a8fa5116b7f16092960bf49509802656c1117c75cc7875c.
        cases = [
            ('', 'da39a3ee5e6b4b0d3255bfef95601890afd80709'),
            ('alpha\nbeta', '0de41d861be31d2da34f42ac07f8f23f9646d44a'),
            ('alpha\n\nbeta\n\n\ngamma', '6d3e4e3ca1d00f99269985eb4f5c2a387b458487'),
            ('  alpha   \t \n   beta  \n\n  gamma  ', '452b9e4475bb8238434fcdd9da975258bbf9716f'),
            ('\x00\x01\x1f alpha\v  beta\f\t gamma\r  delta\x00\x1f', 'a5ad12faba325c57015bc32dc559e36ec48e253a'),
            ('alpha\u00a0  beta\u2003\t gamma', '21fa573e67b5ccd17061d3cb3143a26091672bb7'),
            ('alpha\tbeta', 'c598749ff4816725ecd4cca177d1533e48562b42'),
            ('alpha\r\nbeta', 'a170ee46ff3ac58bf9bb65edf80c41794d4a1414'),
            ('Term: A; B.', '4fb944cb821cc0ed8ee623b81637f1f40210b992'),
            ('alpha\\s   beta', '21036e93135d636d814c7f62120dcf78609ba5b5'),
        ]
        for text, expected in cases:
            with self.subTest(text=repr(text)):
                self.assertEqual(expected, lab.sdk_license_hash(text))

    def package(self, value, accepted, license_id='android-sdk-license', declare=True):
        root = ET.Element('repository')
        if declare:
            ET.SubElement(root, 'license', {'id': license_id}).text = value
        package = ET.SubElement(root, 'remotePackage', {
            'path': 'system-images;android-24;google_apis;x86_64'})
        details = ET.SubElement(package, 'type-details')
        ET.SubElement(details, 'api-level').text = '24'
        ET.SubElement(details, 'abi').text = 'x86_64'
        ET.SubElement(package, 'channelRef', {'ref': 'channel-0'})
        ET.SubElement(package, 'uses-license', {'ref': license_id})
        revision = ET.SubElement(package, 'revision')
        ET.SubElement(revision, 'major').text = '1'
        return lab.parse_feed(root, lab.BASE_URL + lab.FEEDS[1], accepted)[0]

    def test_xml_formatting_uses_bound_sdk_hash_and_preserves_raw_hash(self):
        text = '  alpha\nbeta  \n'
        accepted = {'android-sdk-license': {
            'accepted_sha1': ['0de41d861be31d2da34f42ac07f8f23f9646d44a']}}
        result = self.package(text, accepted)
        self.assertTrue(result['license_already_accepted'])
        self.assertEqual('0de41d861be31d2da34f42ac07f8f23f9646d44a', result['license_text_sha1'])
        self.assertEqual(hashlib.sha1(text.encode()).hexdigest(), result['license_xml_text_sha1'])
        self.assertNotEqual(result['license_text_sha1'], result['license_xml_text_sha1'])

    def test_content_change_remains_unaccepted(self):
        accepted = {'android-sdk-license': {
            'accepted_sha1': ['0de41d861be31d2da34f42ac07f8f23f9646d44a']}}
        self.assertFalse(self.package('alpha BETTER', accepted)['license_already_accepted'])

    def test_other_license_id_does_not_borrow_acceptance(self):
        accepted = {'android-sdk-license': {
            'accepted_sha1': ['0de41d861be31d2da34f42ac07f8f23f9646d44a']}}
        self.assertFalse(self.package('alpha beta', accepted,
                                     'android-sdk-preview-license')['license_already_accepted'])

    def test_raw_hash_is_not_an_accepted_sdk_identity(self):
        text = 'alpha\nbeta'
        accepted = {'android-sdk-license': {
            'accepted_sha1': [hashlib.sha1(text.encode()).hexdigest()]}}
        self.assertFalse(self.package(text, accepted)['license_already_accepted'])

    def test_missing_declared_license_remains_unaccepted(self):
        accepted = {'android-sdk-license': {'accepted_sha1': []}}
        result = self.package('', accepted, declare=False)
        self.assertFalse(result['license_already_accepted'])
        self.assertIsNone(result['license_text_sha1'])

    def test_hashing_does_not_change_the_acceptance_input(self):
        accepted = {'android-sdk-license': {
            'accepted_sha1': ['0de41d861be31d2da34f42ac07f8f23f9646d44a']}}
        before = repr(accepted)
        self.package('alpha\nbeta', accepted)
        self.assertEqual(before, repr(accepted))

    def test_selection_prefers_google_only_among_listed_preaccepted_candidates(self):
        def package(tag, accepted):
            return {'api': 31, 'minor': 0, 'tag': tag, 'abi': 'x86_64', 'revision': [1, 0, 0],
                    'path': 'system-images;android-31;' + tag + ';x86_64',
                    'license_already_accepted': accepted, 'archives': [{'fixture': True}]}
        google, aosp = package('google_apis', False), package('default', True)
        paths = {google['path'], aosp['path']}
        selected = lambda available: next(t for t in lab.choose_targets([google, aosp], available)
                                          if t['api'] == 31)['selected']['path']
        self.assertEqual(aosp['path'], selected(paths))
        google['license_already_accepted'] = True
        self.assertEqual(google['path'], selected(paths))
        self.assertEqual(aosp['path'], selected({aosp['path']}))


if __name__ == '__main__':
    unittest.main()
