#!/usr/bin/env python3
"""Synthetic ELF and ZIP fixtures for the read-only native packaging preflight."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from audit_native_alignment import AuditError, PAGE_SIZE, audit, inspect_elf


def elf(bits=64, endian="<", alignment=PAGE_SIZE, relro_end=None):
    """A bounded synthetic ELF container, not executable Android native code."""
    header, ph = (64, 56) if bits == 64 else (52, 32)
    count = 2 if relro_end is not None else 1
    data = bytearray(header + count * ph + 64)
    data[:7] = b"\x7fELF" + bytes([2 if bits == 64 else 1, 1 if endian == "<" else 2, 1])
    struct.pack_into(endian + "HHI", data, 16, 3, 183 if bits == 64 else 40, 1)
    struct.pack_into(endian + ("Q" if bits == 64 else "I"), data, 32 if bits == 64 else 28, header)
    struct.pack_into(endian + "HHH", data, 52 if bits == 64 else 40, header, ph, count)
    for index in range(count):
        kind = 1 if index == 0 else 0x6474E552
        mem_size = max(len(data), relro_end or 0) if index == 0 else relro_end
        align = alignment if index == 0 else 1
        if bits == 64:
            struct.pack_into(endian + "IIQQQQQQ", data, header + index * ph,
                             kind, 5, 0, 0, 0, len(data) if index == 0 else 0, mem_size, align)
        else:
            struct.pack_into(endian + "IIIIIIII", data, header + index * ph,
                             kind, 0, 0, 0, len(data) if index == 0 else 0, mem_size, 5, align)
    return bytes(data)


def apk(path, content=None, *, align_zip=True, compressed=False, duplicate=False,
        abi="arm64-v8a", manifest=True):
    with zipfile.ZipFile(path, "w") as archive:
        if manifest:
            archive.writestr("AndroidManifest.xml", b"synthetic nonempty manifest placeholder")
        if content is None:
            return
        for _ in range(2 if duplicate else 1):
            name = "lib/" + abi + "/libfixture.so"
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
            if align_zip:
                padding = (-archive.fp.tell() - 30 - len(name.encode("utf-8"))) % PAGE_SIZE
                if padding and padding < 4:
                    padding += PAGE_SIZE
                if padding:
                    info.extra = struct.pack("<HH", 0xCAFE, padding - 4) + bytes(padding - 4)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(info, content)


class ElfTests(unittest.TestCase):
    def test_both_classes_and_byte_orders_are_parsed(self):
        for bits in (32, 64):
            for endian in ("<", ">"):
                with self.subTest(bits=bits, endian=endian):
                    result = inspect_elf(elf(bits, endian))
                    self.assertEqual(bits, result["elf_bits"])
                    self.assertEqual("little" if endian == "<" else "big", result["byte_order"])
                    self.assertEqual([], result["issues"])

    def test_small_64bit_alignment_is_a_finding_not_malformed_input(self):
        for value in (0, 1, 4096, 8192):
            with self.subTest(value=value):
                self.assertEqual(["ELF_LOAD_ALIGNMENT_BELOW_16K"], inspect_elf(elf(alignment=value))["issues"])

    def test_32bit_alignment_is_reported_without_64bit_verdict(self):
        self.assertEqual([], inspect_elf(elf(bits=32, alignment=4096))["issues"])

    def test_non_loadable_segments_do_not_set_load_alignment_verdict(self):
        self.assertEqual([], inspect_elf(elf(relro_end=PAGE_SIZE))["issues"])
        self.assertEqual([], inspect_elf(elf(relro_end=4096))["issues"])

    def test_every_load_segment_is_checked(self):
        data = bytearray(elf(relro_end=PAGE_SIZE))
        struct.pack_into("<I", data, 120, 1)
        struct.pack_into("<Q", data, 120 + 48, 4096)
        self.assertEqual(["ELF_LOAD_ALIGNMENT_BELOW_16K"], inspect_elf(bytes(data))["issues"])

    def test_truncated_headers_and_tables_fail(self):
        valid = elf()
        for size in (0, 4, 16, 63, 100):
            with self.subTest(size=size), self.assertRaises(AuditError):
                inspect_elf(valid[:size])

    def test_invalid_identification_and_shared_object_headers_fail(self):
        for offset, value in ((4, 0), (5, 0), (6, 0), (16, 2), (20, 0), (52, 63), (54, 55), (56, 0)):
            data = bytearray(elf()); data[offset] = value
            with self.subTest(offset=offset), self.assertRaises(AuditError):
                inspect_elf(bytes(data))

    def test_invalid_program_header_counts_offsets_and_segments_fail(self):
        mutations = [(32, "Q", 2**63), (56, "H", 0xFFFF),
                     (64, "I", 0), (64 + 8, "Q", 2**63),
                     (64 + 32, "Q", 2**63), (64 + 40, "Q", 1),
                     (64 + 48, "Q", 3), (64 + 16, "Q", 1)]
        for offset, fmt, value in mutations:
            data = bytearray(elf(relro_end=PAGE_SIZE)); struct.pack_into("<" + fmt, data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(AuditError):
                inspect_elf(bytes(data))

    def test_memory_range_width_and_exact_exclusive_end(self):
        data = bytearray(elf(relro_end=PAGE_SIZE))
        struct.pack_into("<Q", data, 64 + 16, 2**64 - PAGE_SIZE)
        self.assertEqual([], inspect_elf(bytes(data))["issues"])
        struct.pack_into("<Q", data, 64 + 40, PAGE_SIZE + 1)
        with self.assertRaises(AuditError):
            inspect_elf(bytes(data))


class ApkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.apk"

    def test_aligned_stored_library_passes_with_crc_and_hash(self):
        apk(self.path, elf())
        result = audit(self.path)
        self.assertTrue(result["passed"])
        self.assertEqual(1, result["checked_64bit_library_count"])
        self.assertTrue(result["libraries"][0]["native_crc_ok"])
        self.assertTrue(result["libraries"][0]["zip_offset_aligned_16k"])
        self.assertEqual(64, len(result["apk_sha256"]))

    def test_zip_and_elf_failures_are_distinct(self):
        cases = [(elf(), False, ["ZIP_STORED_OFFSET_NOT_ALIGNED_16K"]),
                 (elf(alignment=4096), True, ["ELF_LOAD_ALIGNMENT_BELOW_16K"]),
                 (elf(alignment=4096), False, ["ELF_LOAD_ALIGNMENT_BELOW_16K", "ZIP_STORED_OFFSET_NOT_ALIGNED_16K"])]
        for content, aligned, issues in cases:
            apk(self.path, content, align_zip=aligned)
            with self.subTest(aligned=aligned, issues=issues):
                self.assertEqual(issues, audit(self.path)["findings"][0]["issues"])

    def test_compressed_library_does_not_require_direct_load_zip_alignment(self):
        apk(self.path, elf(), align_zip=False, compressed=True)
        result = audit(self.path)
        self.assertTrue(result["passed"])
        self.assertFalse(result["libraries"][0]["zip_alignment_required"])

    def test_32bit_and_no_native_inputs_are_scoped(self):
        apk(self.path, elf(bits=32, alignment=4096), align_zip=False, abi="armeabi-v7a")
        result = audit(self.path)
        self.assertTrue(result["passed"])
        self.assertEqual(0, result["checked_64bit_library_count"])
        apk(self.path)
        self.assertEqual(0, audit(self.path)["native_library_count"])

    def test_duplicate_missing_manifest_bad_elf_and_wrong_abi_fail(self):
        for kwargs in ({"duplicate": True}, {"manifest": False}, {"abi": "x86"}):
            apk(self.path, elf(), **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(AuditError):
                audit(self.path)
        apk(self.path, b"not an ELF")
        with self.assertRaises(AuditError):
            audit(self.path)

    def test_native_crc_corruption_fails(self):
        apk(self.path, elf())
        result = audit(self.path)
        position = result["libraries"][0]["zip_data_offset"] + len(elf()) - 1
        data = bytearray(self.path.read_bytes()); data[position] ^= 1
        self.path.write_bytes(data)
        with self.assertRaises(zipfile.BadZipFile):
            audit(self.path)

    def test_input_bounds_fail_before_unbounded_reads(self):
        apk(self.path, elf())
        for name, limit in (("MAX_APK_BYTES", 1), ("MAX_ENTRIES", 1),
                            ("MAX_NATIVE_BYTES", 1), ("MAX_TOTAL_NATIVE_BYTES", 1)):
            with self.subTest(bound=name), mock.patch("audit_native_alignment." + name, limit), \
                    self.assertRaises(AuditError):
                audit(self.path)

    def test_local_header_mismatch_fails(self):
        apk(self.path, elf())
        with zipfile.ZipFile(self.path) as archive:
            offset = archive.getinfo("lib/arm64-v8a/libfixture.so").header_offset
        original = self.path.read_bytes()
        for position in (offset, offset + 6, offset + 8, offset + 30):
            data = bytearray(original); data[position] ^= 1; self.path.write_bytes(data)
            with self.subTest(position=position), self.assertRaises(AuditError):
                audit(self.path)

    def test_cli_pass_finding_and_malformed_exit_codes(self):
        script = Path(__file__).with_name("audit_native_alignment.py")
        for data, expected in ((elf(), 0), (elf(alignment=4096), 1), (b"invalid", 2)):
            apk(self.path, data)
            result = subprocess.run([sys.executable, str(script), str(self.path), "--json"],
                                    capture_output=True, text=True, timeout=15)
            with self.subTest(expected=expected):
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertEqual(expected == 0, json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
