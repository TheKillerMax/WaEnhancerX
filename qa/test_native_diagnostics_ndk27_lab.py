#!/usr/bin/env python3
"""Offline failure controls; no downloads, compiler, Android or license writes."""
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import native_diagnostics_ndk27_lab as native


class NativeLabControls(unittest.TestCase):
    def metadata(self):
        root = ET.Element('repository')
        ET.SubElement(root, 'license', {'id': 'android-sdk-license'}).text = 'synthetic test only'
        for package in native.PACKAGES:
            node = ET.SubElement(root, 'remotePackage', {'path': package['path']})
            ET.SubElement(node, 'uses-license', {'ref': 'android-sdk-license'})
            revision = ET.SubElement(node, 'revision')
            for name, value in zip(('major', 'minor', 'micro'), package['revision'].split('.')):
                ET.SubElement(revision, name).text = value
            archive = ET.SubElement(ET.SubElement(node, 'archives'), 'archive')
            ET.SubElement(archive, 'host-os').text = 'linux'
            complete = ET.SubElement(archive, 'complete')
            ET.SubElement(complete, 'size').text = str(package['bytes'])
            ET.SubElement(complete, 'url').text = package['url'].removeprefix(native.lab.BASE_URL)
            ET.SubElement(complete, 'checksum').text = package['sha1']
        return root

    def test_checksum_change_is_blocked_even_with_existing_license(self):
        root = self.metadata()
        accepted = {'android-sdk-license': {'accepted_sha1': [native.LICENSE_SHA1]}}
        with patch.object(native.lab, 'sdk_license_hash', return_value=native.LICENSE_SHA1):
            self.assertEqual(2, len(native.confirm_metadata(root, accepted)))
            root.find('./remotePackage/archives/archive/complete/checksum').text = '0' * 40
            with self.assertRaisesRegex(RuntimeError, 'reviewed pin'):
                native.confirm_metadata(root, accepted)

    def test_license_missing_or_changed_cannot_be_substituted(self):
        root = self.metadata()
        accepted = {'android-sdk-license': {'accepted_sha1': [native.LICENSE_SHA1]}}
        with patch.object(native.lab, 'sdk_license_hash', return_value=native.LICENSE_SHA1):
            with self.assertRaisesRegex(RuntimeError, 'not already registered'):
                native.confirm_metadata(root, {})
        with patch.object(native.lab, 'sdk_license_hash', return_value='1' * 40):
            with self.assertRaisesRegex(RuntimeError, 'reviewed terms'):
                native.confirm_metadata(root, accepted)

    def test_another_license_id_cannot_borrow_standard_acceptance(self):
        root = self.metadata()
        root.find('./remotePackage/uses-license').set('ref', 'android-sdk-preview-license')
        accepted = {'android-sdk-license': {'accepted_sha1': [native.LICENSE_SHA1]}}
        with patch.object(native.lab, 'sdk_license_hash', return_value=native.LICENSE_SHA1):
            with self.assertRaisesRegex(RuntimeError, 'different license'):
                native.confirm_metadata(root, accepted)

    def test_readelf_crosscheck_rejects_a_changed_header(self):
        text = ('  LOAD 0x000000 0x0000000000000000 0x0000000000000000 0x001bd0 0x001bd0 R E 0x1000\n'
                '  GNU_RELRO 0x001bd0 0x0000000000002bd0 0x0000000000002bd0 0x000290 0x000430 R 0x1\n')
        elf = {'load_segments': [{'file_offset': 0, 'virtual_address': 0, 'file_size': 0x1bd0,
                                 'memory_size': 0x1bd0, 'alignment': 0x1000, 'flags': 5}],
               'relro_segments': [{'file_offset': 0x1bd0, 'virtual_address': 0x2bd0,
                                   'file_size': 0x290, 'memory_size': 0x430,
                                   'alignment': 1, 'flags': 4}]}
        self.assertTrue(native.crosscheck_readelf(text, elf))
        with self.assertRaisesRegex(RuntimeError, 'disagree'):
            native.crosscheck_readelf(text.replace('0x1000', '0x4000'), elf)
        with self.assertRaisesRegex(RuntimeError, 'disagree'):
            native.crosscheck_readelf(text.splitlines()[0], elf)

    def test_all_fourteen_exports_required_with_original_binding(self):
        lines = [f'{index}: 0000000000001100 64 FUNC GLOBAL DEFAULT 9 {name}'
                 for index, name in enumerate(native.EXPECTED_JNI, 1)]
        self.assertEqual(native.EXPECTED_JNI, native.jni_exports('\n'.join(lines)))
        for changed in (lines[:-1], lines + [lines[0]],
                        [line.replace('GLOBAL', 'WEAK') for line in lines],
                        [line.replace('DEFAULT 9', 'DEFAULT UND') for line in lines]):
            with self.subTest(changed=changed[-1]):
                with self.assertRaises(RuntimeError):
                    native.jni_exports('\n'.join(changed))


if __name__ == '__main__':
    unittest.main()
