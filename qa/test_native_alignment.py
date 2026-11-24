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


def segmented_elf(segments, *, bits=64, endian="<"):
    """Encode explicit program headers independently of the audit's range logic.

    Tuples are (type, flags, file offset, virtual address, file size, memory
    size, alignment). Payload bytes are placeholders, not executable code.
    """
    header, ph = (64, 56) if bits == 64 else (52, 32)
    length = max(header + ph * len(segments),
                 max(offset + size for _, _, offset, _, size, _, _ in segments))
    data = bytearray(length)
    data[:7] = b"\x7fELF" + bytes([2 if bits == 64 else 1, 1 if endian == "<" else 2, 1])
    struct.pack_into(endian + "HHI", data, 16, 3, 183 if bits == 64 else 40, 1)
    struct.pack_into(endian + ("Q" if bits == 64 else "I"), data, 32 if bits == 64 else 28, header)
    struct.pack_into(endian + "HHH", data, 52 if bits == 64 else 40, header, ph, len(segments))
    for index, (kind, flags, offset, address, size, memory, alignment) in enumerate(segments):
        values = ((kind, flags, offset, address, address, size, memory, alignment)
                  if bits == 64 else
                  (kind, offset, address, address, size, memory, flags, alignment))
        struct.pack_into(endian + ("IIQQQQQQ" if bits == 64 else "IIIIIIII"),
                         data, header + index * ph, *values)
    return bytes(data)


def relro_fixture(*, relro_start=0x5000, relro_end=0x6000,
                  load_end=0x8000, flags=6, extra=(), **kwargs):
    return segmented_elf([
        (1, 5, 0, 0, 0x1000, 0x1000, 0x4000),
        (1, flags, 0x1000, 0x5000, load_end - 0x5000, load_end - 0x5000, 0x4000),
        (0x6474E552, 4, relro_start - 0x4000, relro_start,
         0, relro_end - relro_start, 1),
        *extra,
    ], **kwargs)


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


class RelroTests(unittest.TestCase):
    ISSUE = "ELF_RELRO_OVERLAPS_WRITABLE_16K"

    def test_writable_tail_fails_even_with_aligned_load_headers(self):
        for endian in ("<", ">"):
            with self.subTest(endian=endian):
                report = inspect_elf(relro_fixture(endian=endian))
                self.assertEqual([self.ISSUE], report["issues"])
                self.assertEqual([{"load_segment_index": 1, "start": 0x6000,
                                   "end": 0x8000}], report["relro_writable_overlaps"])

    def test_readonly_tail_is_not_a_writable_data_finding(self):
        self.assertEqual([], inspect_elf(relro_fixture(flags=4))["issues"])

    def test_aligned_end_and_exact_end_of_load_are_safe(self):
        for options in ({"relro_end": 0x8000, "load_end": 0x9000},
                        {"load_end": 0x6000}):
            with self.subTest(options=options):
                self.assertEqual([], inspect_elf(relro_fixture(**options))["issues"])

    def test_one_byte_before_page_boundary_is_a_finding(self):
        report = inspect_elf(relro_fixture(relro_end=0x7fff))
        self.assertEqual([self.ISSUE], report["issues"])
        self.assertEqual(0x7fff, report["relro_writable_overlaps"][0]["start"])
        self.assertEqual(0x8000, report["relro_writable_overlaps"][0]["end"])
        self.assertEqual([], inspect_elf(relro_fixture(relro_end=0x8000))["issues"])

    def test_relro_padding_beyond_load_is_not_rejected(self):
        self.assertEqual([], inspect_elf(relro_fixture(relro_end=0x7000,
                                                       load_end=0x6000))["issues"])

    def test_next_writable_load_must_not_share_relro_trailing_page(self):
        for address, expected in ((0x7000, [self.ISSUE]), (0x8000, [])):
            next_load = (1, 6, address - 0x4000, address, 0, 0x1000, 0x4000)
            report = inspect_elf(relro_fixture(load_end=0x6000, extra=[next_load]))
            with self.subTest(address=address):
                self.assertEqual(expected, report["issues"])

    def test_start_rounding_detects_writable_prefix(self):
        report = inspect_elf(relro_fixture(relro_start=0x6000, relro_end=0x8000))
        self.assertEqual([self.ISSUE], report["issues"])
        self.assertEqual([{"load_segment_index": 1, "start": 0x5000,
                           "end": 0x6000}], report["relro_writable_overlaps"])

    def test_multiple_relro_ranges_cover_each_other_but_not_gaps(self):
        for start, expected in ((0x6000, []), (0x7000, [self.ISSUE])):
            second = (0x6474E552, 4, start - 0x4000, start, 0, 0x8000 - start, 1)
            report = inspect_elf(relro_fixture(extra=[second]))
            with self.subTest(start=start):
                self.assertEqual(expected, report["issues"])

    def test_empty_relro_uses_actual_page_rounding_without_certifying_32bit(self):
        self.assertEqual([self.ISSUE], inspect_elf(relro_fixture(
            relro_start=0x5000, relro_end=0x5000))["issues"])
        self.assertEqual([], inspect_elf(relro_fixture(
            relro_start=0x8000, relro_end=0x8000))["issues"])
        report = inspect_elf(relro_fixture(bits=32))
        self.assertEqual([], report["issues"])
        self.assertFalse(report["relro_alignment_checked"])
        self.assertEqual(1, len(report["relro_segments"]))

    def test_relro_file_and_memory_bounds_are_validated(self):
        # The third ELF64 header is GNU_RELRO; alter one field at a time.
        start = 64 + 2 * 56
        for offset, value in ((8, 2**63), (32, 2**63), (32, 0x1001),
                              (16, 2**64 - 1), (48, 3)):
            data = bytearray(relro_fixture())
            struct.pack_into("<Q", data, start + offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(AuditError):
                inspect_elf(bytes(data))

    def test_documented_relro_examples(self):
        # Explicit program headers from Android's 16 KiB guide, examples 1, 2,
        # and 4. They cover shared RW data, aligned end, and a separate LOAD.
        examples = [
            ([(1, 5, 0, 0, 0xcfaf0, 0xcfaf0, 0x4000),
              (1, 6, 0xcfaf0, 0xdfaf0, 0x2510, 0x4510, 0x4000),
              (0x6474E552, 4, 0xcfaf0, 0xdfaf0, 0x1510, 0x1510, 1)], [self.ISSUE]),
            ([(1, 5, 0, 0, 0xcfaf0, 0xcfaf0, 0x4000),
              (1, 6, 0xcfaf0, 0xdfaf0, 0x1510, 0x3510, 0x4000),
              (0x6474E552, 4, 0xcfaf0, 0xdfaf0, 0x510, 0x510, 1)], []),
            ([(1, 5, 0, 0, 0x680, 0x680, 0x4000),
              (1, 6, 0x680, 0x4680, 0x1d8, 0x980, 0x4000),
              (0x6474E552, 4, 0x680, 0x4680, 0x1d8, 0x980, 1)], []),
        ]
        for index, (segments, expected) in enumerate(examples):
            with self.subTest(example=index):
                self.assertEqual(expected, inspect_elf(segmented_elf(segments))["issues"])


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

    def test_relro_finding_survives_compression_and_cli_reports_schema_two(self):
        apk(self.path, relro_fixture(), compressed=True)
        script = Path(__file__).with_name("audit_native_alignment.py")
        result = subprocess.run([sys.executable, str(script), str(self.path), "--json"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(2, report["schema_version"])
        self.assertFalse(report["passed"])
        self.assertEqual([RelroTests.ISSUE], report["findings"][0]["issues"])
        self.assertTrue(report["libraries"][0]["relro_alignment_checked"])


if __name__ == "__main__":
    unittest.main()
