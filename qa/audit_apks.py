#!/usr/bin/env python3
"""Perform a conservative, read-only APK/DEX compatibility preflight.

Usage: python3 qa/audit_apks.py WAEX.apk WhatsApp.apk [--json] [--strict-anchors]

Check ZIP CRC, DEX header/hash consistency, declared native ABIs, and a small
historical sample of literal DexKit search strings within DEX string pools.
A literal match does NOT prove that any Xposed hook resolves or works, while an
absent literal does NOT rule out other search strategies. In particular, this
is not an Android build, method-signature test, APK signing verification, or
runtime LSPosed test. Never commit the input APKs to a public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
import zlib
from pathlib import Path

# Snapshot of 18 historical literal DexKit anchors used in WAEX. These are
# diagnostics, not a complete list of hooks or a compatibility allowlist.
ANCHORS = {
    "Read receipts": "ReadReceipts/sendReceiptForIncomingMessage",
    "Call recording callback": "VoiceServiceEventCallback",
    "Image compression": "image/compress quality",
    "Video frame rate": "video/encoder fps",
    "Message sender JID": "FMessage/getSenderUserJid/key.id",
    "Typing presence": "HandleMeComposing/sendComposing",
    "Availability": "presencestatemanager/startTransitionToUnavailable/new-state",
    "Pinned chats limit": "pininfo/setpin/failed-already-max-pinned",
    "View-once SQL": "INSERT_VIEW_ONCE_SQL",
    "Send message event": "app/sendmessage/message_sent",
    "Voice-call state": "voip/callStateChangedOnUIThread",
    "Message handler": "MessageHandler/start",
    "Presence receive": "app/xmpp/recv/handle_available",
    "Status playback": "playbackPage/onPlaybackContentFinished",
    "Chat info events": "chatInfo/incrementUnseenImportantMessageCount",
    "Channel subscription": "hasNewsletterSubscriptions",
    "Archive preview": "archive/set-content-indicator-to-empty",
    "Chat bubble drawable": "balloon_incoming_normal",
}

DEX_ENTRY = re.compile(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex\Z")
HEADER_SIZE = 112
MAX_DEX_SIZE = 256 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100_000
MAX_DEX_STRING_BYTES = 2 * 1024 * 1024
MAX_DEX_STRING_ITEMS = 4_000_000


class AuditError(Exception):
    """Malformed or inconsistent APK input; avoid misleading partial reports."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_uleb128(data: bytes, offset: int) -> int:
    for shift in (0, 7, 14, 21, 28):
        _check(offset < len(data), "Truncated DEX string length")
        value = data[offset]
        offset += 1
        if value < 128:
            return offset
    raise AuditError("Invalid DEX string length ULEB128")


def _dex_strings(dex: bytes):
    _check(len(dex) >= HEADER_SIZE, "Truncated DEX header")
    _check(dex.startswith(b"dex\n") and dex[4:7].isdigit() and dex[7] == 0,
           "Invalid DEX magic/version")
    declared_length, header_size = struct.unpack_from("<II", dex, 0x20)
    _check(declared_length == len(dex), "DEX file_size does not match content")
    _check(header_size in (112, 120), "Unsupported DEX header size")
    _check(dex[12:32] == hashlib.sha1(dex[32:]).digest(), "DEX SHA-1 header mismatch")
    _check(struct.unpack_from("<I", dex, 8)[0] == zlib.adler32(dex[12:]),
           "DEX Adler-32 header mismatch")

    count, ids_offset = struct.unpack_from("<II", dex, 0x38)
    _check(count <= MAX_DEX_STRING_ITEMS, "Unreasonable DEX string count")
    _check(ids_offset <= len(dex) and count * 4 <= len(dex) - ids_offset,
           "DEX string_ids section out of bounds")
    for (offset,) in struct.iter_unpack("<I", memoryview(dex)[ids_offset: ids_offset + 4 * count]):
        _check(offset < len(dex), "DEX string_data offset out of bounds")
        string_begin = _decode_uleb128(dex, offset)
        string_end = dex.find(b"\x00", string_begin,
                              min(len(dex), string_begin + MAX_DEX_STRING_BYTES + 1))
        _check(string_end >= 0, "Unterminated or oversized DEX string")
        yield dex[string_begin:string_end]


def _inspect(path: Path, *, scan_anchors: bool) -> tuple[dict, dict[str, bool]]:
    _check(path.is_file(), f"APK not found: {path.name}")
    _check(path.stat().st_size > 0, f"Empty APK: {path.name}")
    remaining = {label: literal.encode("ascii") for label, literal in ANCHORS.items()} if scan_anchors else {}
    found: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            _check(len(entries) <= MAX_ARCHIVE_ENTRIES, "APK ZIP has excessive entries")
            _check(sum(x.file_size for x in entries) <= MAX_ARCHIVE_UNCOMPRESSED,
                   "APK ZIP total uncompressed size exceeds audit limit")
            _check(all(x.file_size >= 0 for x in entries), "Invalid ZIP member size")
            names = [x.filename for x in entries]
            _check(names.count("AndroidManifest.xml") == 1, "Missing or duplicate AndroidManifest.xml")
            _check(archive.getinfo("AndroidManifest.xml").file_size > 0, "Empty AndroidManifest.xml")
            dex = [member for member in entries if DEX_ENTRY.fullmatch(member.filename)]
            _check(dex, "APK contains no classes*.dex")
            _check(len(set(x.filename for x in dex)) == len(dex), "Duplicate DEX entry names")
            _check(any(x.filename == "classes.dex" for x in dex), "Primary classes.dex is missing")
            _check(all(x.file_size <= MAX_DEX_SIZE for x in dex), "Oversized DEX entry")
            corrupted = archive.testzip()
            _check(corrupted is None, f"ZIP CRC mismatch: {corrupted}")
            for entry in dex:
                data = archive.read(entry)
                # Even when no string scanning is requested, verify the DEX
                # container and its internal hashes. Exhaust every generator.
                for literal in _dex_strings(data):
                    if remaining and len(literal) >= 12:
                        for label, needle in tuple(remaining.items()):
                            if needle in literal:
                                found.add(label)
                                del remaining[label]
            abis = sorted({name.split("/")[1] for name in names
                           if name.startswith("lib/") and len(name.split("/")) >= 3
                           and name.endswith(".so")})
            report = {
                "file": path.name,
                "sha256": _sha256(path),
                "zip_entries": len(entries),
                "zip_crc_ok": True,
                "dex_files": len(dex),
                "dex_names": sorted(x.filename for x in dex),
                "native_abis": abis,
            }
            return report, {label: label in found for label in ANCHORS} if scan_anchors else {}
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, OverflowError, EOFError) as err:
        raise AuditError(f"Invalid APK '{path.name}': {err}") from err


def audit(manager: Path, host: Path) -> dict:
    _check(manager.resolve() != host.resolve(), "Manager and WhatsApp must be different APKs")
    manager_summary, _ = _inspect(manager, scan_anchors=False)
    host_summary, presence = _inspect(host, scan_anchors=True)
    results = {label: {"literal": text, "present": presence[label]}
               for label, text in ANCHORS.items()}
    return {
        "schema_version": 1,
        "manager": manager_summary,
        "host": host_summary,
        "literal_anchor_sample": results,
        "anchor_count": len(results),
        "anchors_found": sum(1 for p in presence.values() if p),
        "disclaimer": ("DEX literal presence/absence is not method-resolution or hook functionality "
                       "verification; this does not validate signing certificates, ELF page alignment, "
                       "Android builds, device behavior or WhatsApp version compatibility."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("waex_apk", type=Path)
    parser.add_argument("whatsapp_apk", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of a text summary")
    parser.add_argument("--strict-anchors", action="store_true",
                        help="Exit 3 if one of the sampled literals is absent (NOT a full compatibility test)")
    args = parser.parse_args(argv)
    try:
        report = audit(args.waex_apk, args.whatsapp_apk)
    except AuditError as err:
        print(f"APK audit failed: {err}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        for who in ("manager", "host"):
            item = report[who]
            print(f"{who.capitalize()}: {item['file']} — {item['zip_entries']} ZIP entries, "
                  f"{item['dex_files']} DEX, ABI {item['native_abis']}, CRC+DEX integrity OK")
        print(f"Sampled literal anchors: {report['anchors_found']}/{report['anchor_count']} "
              "(NOT hook functionality verification)")
        for label, item in report["literal_anchor_sample"].items():
            print(f"  {'FOUND' if item['present'] else 'MISSING':7} {label}: {item['literal']}")
        print(report["disclaimer"])
    return 3 if args.strict_anchors and report["anchors_found"] < report["anchor_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
