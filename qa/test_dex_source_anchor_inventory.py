#!/usr/bin/env python3
"""Synthetic DEX/source regression tests; no proprietary host files are required."""
import contextlib
import hashlib
import io
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from dex_source_anchor_inventory import AuditError, source_anchors, audit, main


def uleb(n):
    encoded = bytearray()
    while True:
        b = n & 127
        n >>= 7
        encoded.append(b | (128 if n else 0))
        if not n:
            return bytes(encoded)


def dex_with(strings):
    header = bytearray(112)
    header[:8] = b'dex\n035\x00'
    struct.pack_into('<I', header, 0x24, 112)
    struct.pack_into('<II', header, 0x38, len(strings), 112)
    table = bytearray()
    payload = bytearray()
    for text in strings:
        utf8 = text.encode('utf8')
        offset = 112 + 4 * len(strings) + len(payload)
        table.extend(struct.pack('<I', offset))
        payload.extend(uleb(len(text)) + utf8 + b'\x00')
    result = header + table + payload
    struct.pack_into('<I', result, 0x20, len(result))
    result[12:32] = hashlib.sha1(result[32:]).digest()
    struct.pack_into('<I', result, 8, zlib.adler32(result[12:]))
    return bytes(result)


class DexSourceAnchorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='waex_source_dex_')
        self.root = Path(self.tmp.name)
        self.src = self.root / 'src'
        self.src.mkdir()
        (self.src / 'A.java').write_text('''class A {
 void test() {
   addUsingString("image/compress quality", StringMatchType.Contains);
   addUsingString("shared anchor", StringMatchType.Contains);
   addUsingString(dynamicName);
 }
}
''')
        (self.src / 'B.kt').write_text('''fun hook() {
 addUsingString("shared anchor", StringMatchType.Contains)
 addUsingString(
    "DeleteMessageForMeMutation",
    StringMatchType.Contains)
}
''')
        self.apk = self.root / 'synthetic.apk'
        self.make_apk()

    def tearDown(self):
        self.tmp.cleanup()

    def make_apk(self, corrupt=False):
        primary = dex_with(['fake unrelated private string', 'prefix shared anchor suffix'])
        secondary = dex_with(['image/compress quality in diagnostic'])
        if corrupt:
            secondary = secondary[:-1] + bytes([secondary[-1] ^ 1])
        with zipfile.ZipFile(self.apk, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr('AndroidManifest.xml', b'fixture manifest')
            z.writestr('classes.dex', primary)
            z.writestr('classes2.dex', secondary)

    def test_literal_source_extraction_and_sites(self):
        anchors = source_anchors(self.src)
        self.assertEqual(set(anchors), {'image/compress quality', 'shared anchor', 'DeleteMessageForMeMutation'})
        self.assertEqual(len(anchors['shared anchor']), 2)
        self.assertEqual(anchors['image/compress quality'][0]['line'], 3)

    def test_real_dex_string_ids_only(self):
        report = audit(self.apk, self.src)
        self.assertEqual(report['anchor_count'], 3)
        self.assertEqual(report['anchors_present'], 2)
        self.assertEqual(report['anchors_missing'], 1)
        self.assertEqual(report['dex_files_checked'], 2)
        self.assertNotIn('fake unrelated private string', str(report))
        missing = [x['literal'] for x in report['anchors'] if not x['present']]
        self.assertEqual(missing, ['DeleteMessageForMeMutation'])

    def test_strict_cli_exit_three(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([str(self.apk), '--source-root', str(self.src), '--strict']), 3)
        self.assertIn('ABSENT DeleteMessageForMeMutation', output.getvalue())

    def test_valid_cli_exit_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.apk), '--source-root', str(self.src)]), 0)

    def test_bad_dex_hash_rejected(self):
        self.make_apk(corrupt=True)
        with self.assertRaisesRegex(AuditError, 'SHA-1 mismatch'):
            audit(self.apk, self.src)

    def test_missing_or_invalid_apk(self):
        with self.assertRaises(AuditError):
            audit(self.root / 'absent.apk', self.src)
        with self.assertRaises(AuditError):
            source_anchors(self.root / 'absent-source')

    def test_unused_bytes_do_not_count_as_string_id(self):
        extra = dex_with(['valid only']) + b'DeleteMessageForMeMutation'
        # Extra bytes violate the DEX file_size header; reseal to keep the fixture valid.
        result = bytearray(extra)
        struct.pack_into('<I', result, 0x20, len(result))
        result[12:32] = hashlib.sha1(result[32:]).digest()
        struct.pack_into('<I', result, 8, zlib.adler32(result[12:]))
        with zipfile.ZipFile(self.apk, 'w') as z:
            z.writestr('classes.dex', bytes(result))
        report = audit(self.apk, self.src)
        self.assertEqual(report['anchors_present'], 0)


if __name__ == '__main__':
    unittest.main()
