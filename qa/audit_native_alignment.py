#!/usr/bin/env python3
"""Read-only 16 KiB native-library packaging preflight for a supplied APK.

Check ELF headers/program headers in every lib/<abi>/*.so, then require 64-bit
PT_LOAD alignment and 16 KiB ZIP offsets for stored
64-bit libraries. Compressed libraries do not require a direct-load ZIP offset.
32-bit libraries are structurally parsed and reported, not certified for 16 KiB.

This is a conservative packaging gate, not APK authentication, resource checking,
Android linker execution or proof of device compatibility. It never rewrites an
APK or rebuilds a dependency. Exit 0: checks pass; 1: alignment findings;
2: malformed/unsupported/bounded input or I/O failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

PAGE_SIZE = 16 * 1024
MAX_APK_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_NATIVE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_NATIVE_BYTES = 512 * 1024 * 1024
MAX_PROGRAM_HEADERS = 4096
NATIVE = re.compile(r"lib/([^/.][^/]*)/([^/]+\.so)\Z")
PT_LOAD = 1


class AuditError(ValueError):
    """An invalid input must not produce a partial green report."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def inspect_elf(data: bytes) -> dict:
    require(len(data) >= 16 and data[:4] == b"\x7fELF", "Missing ELF identification")
    elf_class, encoding, identification_version = data[4:7]
    require(elf_class in (1, 2), "Unsupported ELF class")
    require(encoding in (1, 2), "Unsupported ELF byte order")
    require(identification_version == 1, "Unsupported ELF identification version")
    endian = "<" if encoding == 1 else ">"
    bits = 32 if elf_class == 1 else 64
    header_size, ph_size = (52, 32) if bits == 32 else (64, 56)
    require(len(data) >= header_size, "Truncated ELF header")
    file_type, machine, version = struct.unpack_from(endian + "HHI", data, 16)
    require(file_type == 3, "Native library must be an ELF shared object (ET_DYN)")
    require(version == 1, "Unsupported ELF header version")
    ph_offset = struct.unpack_from(endian + ("I" if bits == 32 else "Q"),
                                  data, 28 if bits == 32 else 32)[0]
    declared_size, entry_size, count = struct.unpack_from(
        endian + "HHH", data, 40 if bits == 32 else 52)
    require(declared_size == header_size, "Incorrect ELF header size")
    require(entry_size == ph_size, "Incorrect ELF program-header size")
    require(0 < count <= MAX_PROGRAM_HEADERS, "Unsupported ELF program-header count")
    require(header_size <= ph_offset <= len(data), "ELF program-header offset out of bounds")
    require(count * entry_size <= len(data) - ph_offset, "Truncated ELF program-header table")
    loads = []
    for index in range(count):
        offset = ph_offset + index * entry_size
        if bits == 64:
            kind, flags, file_offset, address, _, file_size, mem_size, alignment = \
                struct.unpack_from(endian + "IIQQQQQQ", data, offset)
        else:
            kind, file_offset, address, _, file_size, mem_size, flags, alignment = \
                struct.unpack_from(endian + "IIIIIIII", data, offset)
        if kind != PT_LOAD:
            continue
        require(file_offset <= len(data) and file_size <= len(data) - file_offset,
                "ELF segment file range out of bounds")
        require(file_size <= mem_size, "ELF file segment exceeds memory size")
        require(address + mem_size <= (1 << bits), "ELF memory range overflows its address width")
        require(alignment in (0, 1) or alignment & (alignment - 1) == 0,
                "ELF segment alignment is not a power of two")
        if alignment > 1:
            require(file_offset % alignment == address % alignment,
                    "ELF file and virtual offsets violate segment alignment")
        item = {"index": index, "file_offset": file_offset, "virtual_address": address,
                "file_size": file_size, "memory_size": mem_size, "alignment": alignment}
        loads.append(item)
    require(bool(loads), "ELF has no loadable segment")
    issues = []
    if bits == 64:
        if any(segment["alignment"] < PAGE_SIZE for segment in loads):
            issues.append("ELF_LOAD_ALIGNMENT_BELOW_16K")
    return {"elf_bits": bits, "machine": machine,
            "byte_order": "little" if encoding == 1 else "big",
            "load_segments": loads, "issues": issues}


def zip_data_offset(stream, entry: zipfile.ZipInfo, apk_size: int) -> int:
    require(0 <= entry.header_offset <= apk_size - 30, "ZIP local header out of bounds")
    stream.seek(entry.header_offset)
    header = stream.read(30)
    require(len(header) == 30 and header[:4] == b"PK\x03\x04", "Invalid ZIP local header")
    flags, method = struct.unpack_from("<HH", header, 6)
    name_size, extra_size = struct.unpack_from("<HH", header, 26)
    require(flags == entry.flag_bits and method == entry.compress_type,
            "ZIP local/central flags or compression disagree")
    require(not flags & 1, "Encrypted native libraries are unsupported")
    offset = entry.header_offset + 30 + name_size + extra_size
    require(offset <= apk_size and entry.compress_size <= apk_size - offset,
            "ZIP native payload out of bounds")
    raw_name = stream.read(name_size)
    try:
        name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
    except UnicodeDecodeError as error:
        raise AuditError("Invalid ZIP member name") from error
    require(name == entry.filename, "ZIP local/central filenames disagree")
    return offset


def audit(apk: Path) -> dict:
    require(apk.is_file(), "APK input does not exist")
    size = apk.stat().st_size
    require(0 < size <= MAX_APK_BYTES, "APK size exceeds input bounds or is empty")
    digest = hashlib.sha256()
    with apk.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    libraries = []
    with apk.open("rb") as raw, zipfile.ZipFile(apk) as archive:
        entries = archive.infolist()
        require(len(entries) <= MAX_ENTRIES, "APK has excessive ZIP entries")
        manifests = [entry for entry in entries if entry.filename == "AndroidManifest.xml"]
        require(len(manifests) == 1 and manifests[0].file_size > 0,
                "APK requires one nonempty AndroidManifest.xml entry")
        native = [entry for entry in entries if NATIVE.fullmatch(entry.filename)]
        require(len({entry.filename for entry in native}) == len(native), "Duplicate native ZIP entry")
        require(all(0 < entry.file_size <= MAX_NATIVE_BYTES for entry in native),
                "Native member size exceeds input bounds or is empty")
        require(sum(entry.file_size for entry in native) <= MAX_TOTAL_NATIVE_BYTES,
                "Total native size exceeds input bound")
        for entry in sorted(native, key=lambda item: item.filename):
            require(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "Unsupported native ZIP compression")
            offset = zip_data_offset(raw, entry, size)
            # zipfile validates the complete native member CRC as it is consumed.
            with archive.open(entry) as reader:
                data = reader.read(entry.file_size + 1)
            require(len(data) == entry.file_size, "Native member decompressed size mismatch")
            try:
                result = inspect_elf(data)
            except AuditError as error:
                raise AuditError(entry.filename + ": " + str(error)) from error
            abi = entry.filename.split("/")[1]
            expected = {"arm64-v8a": (64, 183), "x86_64": (64, 62),
                        "armeabi-v7a": (32, 40), "x86": (32, 3)}.get(abi)
            if expected:
                require((result["elf_bits"], result["machine"]) == expected,
                        entry.filename + ": ELF class/machine disagree with ABI directory")
            stored = entry.compress_type == zipfile.ZIP_STORED
            zip_required = stored and result["elf_bits"] == 64
            if zip_required and offset % PAGE_SIZE:
                result["issues"].append("ZIP_STORED_OFFSET_NOT_ALIGNED_16K")
            result.update({"entry": entry.filename, "abi": abi, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest(), "native_crc_ok": True,
                           "zip_stored": stored, "zip_data_offset": offset,
                           "zip_alignment_required": zip_required,
                           "zip_offset_aligned_16k": offset % PAGE_SIZE == 0,
                           "alignment_checked": result["elf_bits"] == 64})
            libraries.append(result)
    findings = [{"entry": library["entry"], "issues": library["issues"]}
                for library in libraries if library["issues"]]
    return {"schema_version": 1, "apk": apk.name, "apk_sha256": digest.hexdigest(),
            "page_size": PAGE_SIZE, "native_library_count": len(libraries),
            "checked_64bit_library_count": sum(library["alignment_checked"] for library in libraries),
            "libraries": libraries, "findings": findings, "passed": not findings,
            "scope": ("64-bit ELF PT_LOAD and stored native ZIP offsets; "
                      "native-entry CRC only, not APK signatures, resources, linker execution "
                      "or device compatibility. Stored offsets are checked conservatively "
                      "for direct loading; the binary manifest extraction policy, GNU_RELRO "
                      "protection layout and non-loadable segments are not validated.")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit(args.apk)
    except (OSError, AuditError, zipfile.BadZipFile, RuntimeError, EOFError,
            struct.error, NotImplementedError) as error:
        print(json.dumps({"passed": False, "input_error": str(error)}))
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['apk']}: {report['checked_64bit_library_count']} 64-bit libraries checked, "
              f"{len(report['findings'])} libraries with alignment findings")
        for finding in report["findings"]:
            print(f"  {finding['entry']}: {', '.join(finding['issues'])}")
        print(report["scope"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
