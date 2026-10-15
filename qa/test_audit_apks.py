#!/usr/bin/env python3
"""Synthetic APK/DEX fixtures for the read-only QA auditor (standard library only)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import struct
import tempfile
import unittest
import warnings
import zipfile
import zlib
from pathlib import Path

from audit_apks import ANCHORS, AuditError, DEX_ENTRY, audit, main


def _uleb128(value: int) -> bytes:
    result = bytearray()
    while True:
        group = value & 0x7f
        value >>= 7
        result.append(group | (0x80 if value else 0))
        if value == 0:
            return bytes(result)


def _reseal(data: bytes) -> bytes:
    result = bytearray(data)
    struct.pack_into("<I", result, 0x20, len(result))
    result[12:32] = hashlib.sha1(result[32:]).digest()
    struct.pack_into("<I", result, 8, zlib.adler32(result[12:]))
    return bytes(result)


def make_dex(strings: list[str], *, noise: bytes = b"") -> bytes:
    """Build a minimal test DEX with correct header and string ID table.

    No class/method definitions are needed because the auditor intentionally
    checks *literal strings*, not loadability or hook functionality.
    """
    header = bytearray(112)
    header[:8] = b"dex\n035\0"
    struct.pack_into("<I", header, 0x24, 112)
    ids_offset = 112
    struct.pack_into("<II", header, 0x38, len(strings), ids_offset)
    strings_bytes = bytearray()
    table = bytearray()
    data_offset = ids_offset + len(strings) * 4
    for raw in strings:
        utf8 = raw.encode("utf-8")
        # All test anchors are ASCII. Length is tracked in UTF-16 code units.
        utf16_units = len(raw.encode("utf-16-le")) // 2
        table.extend(struct.pack("<I", data_offset + len(strings_bytes)))
        strings_bytes.extend(_uleb128(utf16_units) + utf8 + b"\0")
    return _reseal(header + table + strings_bytes + noise)


def make_apk(path: Path, *, dex: dict[str, bytes] | None = None,
             manifest: bytes | None = b"android-binary-manifest-stub",
             abi: str | None = None, extra: dict[str, bytes] | None = None,
             compression: int = zipfile.ZIP_DEFLATED) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        if manifest is not None:
            archive.writestr("AndroidManifest.xml", manifest)
        for name, data in (dex if dex is not None else {"classes.dex": make_dex(["Synthetic test string"])}).items():
            archive.writestr(name, data)
        if abi:
            archive.writestr(f"lib/{abi}/libsynthetic.so", b"not-an-ELF")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)


class ApkAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="waex_audit_test_")
        self.home = Path(self.tmp.name)
        self.manager = self.home / "WAEX-test.apk"
        self.host = self.home / "WhatsApp-test.apk"
        make_apk(self.manager, abi="arm64-v8a")
        self.matched_label, self.matched_literal = next(iter(ANCHORS.items()))
        make_apk(self.host, dex={"classes.dex": make_dex([self.matched_literal])})

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_reports_only_existing_pool_literal(self):
        report = audit(self.manager, self.host)
        self.assertEqual(report["anchor_count"], 18)
        self.assertEqual(report["anchors_found"], 1)
        self.assertTrue(report["literal_anchor_sample"][self.matched_label]["present"])
        self.assertTrue(report["manager"]["zip_crc_ok"])
        self.assertEqual(report["manager"]["native_abis"], ["arm64-v8a"])
        self.assertEqual(report["host"]["dex_files"], 1)
        self.assertEqual(len(report["host"]["sha256"]), 64)
        self.assertEqual(report["manager"]["file"], "WAEX-test.apk")
        self.assertNotIn(str(self.home), json.dumps(report))

    def test_multidex_names_include_ten_twelve(self):
        self.assertTrue(DEX_ENTRY.fullmatch("classes.dex"))
        self.assertTrue(DEX_ENTRY.fullmatch("classes2.dex"))
        self.assertTrue(DEX_ENTRY.fullmatch("classes10.dex"))
        self.assertTrue(DEX_ENTRY.fullmatch("classes12.dex"))
        self.assertFalse(DEX_ENTRY.fullmatch("classes1.dex"))
        self.assertFalse(DEX_ENTRY.fullmatch("classes0.dex"))
        self.assertFalse(DEX_ENTRY.fullmatch("nested/classes2.dex"))
        make_apk(self.host, dex={"classes.dex": make_dex(["first"]),
                                 "classes2.dex": make_dex([self.matched_literal]),
                                 "classes10.dex": make_dex(["tenth"]),
                                 "classes11.dex": make_dex(["eleventh"]),
                                 "classes12.dex": make_dex(["twelfth"])})
        summary = audit(self.manager, self.host)
        self.assertEqual(summary["host"]["dex_files"], 5)
        self.assertTrue(summary["literal_anchor_sample"][self.matched_label]["present"])

    def test_absence_does_not_scan_arbitrary_unused_bytes(self):
        make_apk(self.host, dex={"classes.dex": make_dex(["string_without_target"],
                            noise=self.matched_literal.encode("ascii"))})
        report = audit(self.manager, self.host)
        self.assertEqual(report["anchors_found"], 0)

    def test_empty_nonfile_and_same_path(self):
        with self.assertRaises(AuditError):
            audit(self.manager, self.manager)
        with self.assertRaises(AuditError):
            audit(self.manager, self.home / "missing.apk")
        self.host.write_bytes(b"")
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)

    def test_non_zip_rejected(self):
        self.host.write_bytes(b"not an APK")
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)

    def test_missing_duplicate_or_empty_manifest(self):
        make_apk(self.host, manifest=None)
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)
        make_apk(self.host, manifest=b"")
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.host, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"one")
                archive.writestr("AndroidManifest.xml", b"two")
                archive.writestr("classes.dex", make_dex(["other"]))
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)

    def test_missing_primary_or_all_dex_rejected(self):
        make_apk(self.host, dex={})
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)
        make_apk(self.host, dex={"classes2.dex": make_dex(["other"])})
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)

    def test_bad_zip_member_crc_rejected(self):
        make_apk(self.host, compression=zipfile.ZIP_STORED,
                 extra={"assets/test.txt": b"unique marker for CRC tampering"})
        raw = self.host.read_bytes()
        marker = b"unique marker for CRC tampering"
        self.assertEqual(raw.count(marker), 1)
        self.host.write_bytes(raw.replace(marker, marker[:-1] + b"!"))
        with self.assertRaises(AuditError):
            audit(self.manager, self.host)

    def test_bad_dex_header_magic_checksum_and_length(self):
        original = make_dex(["some text"])
        for bad in [b"bad\n" + original[4:], original[:-1],
                    original[:12] + b"\x00" + original[13:],
                    original[:8] + b"\x00" + original[9:]]:
            make_apk(self.host, dex={"classes.dex": bad})
            with self.subTest(data=bad[:9]):
                with self.assertRaises(AuditError):
                    audit(self.manager, self.host)

    def test_corrupt_dex_offsets_even_when_hashes_match(self):
        source = bytearray(make_dex(["hello"]))
        struct.pack_into("<I", source, 112, len(source) + 500)
        make_apk(self.host, dex={"classes.dex": _reseal(source)})
        with self.assertRaisesRegex(AuditError, "offset out of bounds"):
            audit(self.manager, self.host)

    def test_cli_json_and_optional_strict_mode(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main([str(self.manager), str(self.host), "--json"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["anchors_found"], 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.manager), str(self.host), "--strict-anchors"]), 3)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.manager), "missing.apk"]), 2)

    def test_dex_without_any_strings_is_valid(self):
        make_apk(self.host, dex={"classes.dex": make_dex([])})
        report = audit(self.manager, self.host)
        self.assertEqual(report["anchors_found"], 0)


if __name__ == "__main__":
    unittest.main()
