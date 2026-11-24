# Native-library alignment acceptance

`audit_native_alignment.py` is a read-only packaging diagnostic for an APK
supplied locally. It inspects every native ELF header and program-header table,
checks native member CRCs, and reports SHA-256 identities. For 64-bit libraries it
checks each `PT_LOAD` alignment, GNU_RELRO page-rounding overlap with writable
LOAD ranges, and ZIP data offsets for uncompressed libraries. These are separate checks: a ZIP-aligned library can
still contain ELF segments aligned to only 4 KiB.

```sh
python3 qa/audit_native_alignment.py /path/to/module.apk --json
python3 qa/test_native_alignment.py
```

JSON schema version 2 retains the previous keys and adds LOAD permission flags,
RELRO segment metadata, `relro_alignment_checked`, and
`relro_writable_overlaps`. Consumers that require schema version 1 must accept
version 2 explicitly: an input can now fail an additional RELRO check.

Exit 0 means these packaging checks passed; 1 reports alignment findings; 2 means
the input was malformed, unsupported, out of bounds, or unreadable. A missing
native directory is reported as zero native libraries checked. The tool parses
32-bit libraries but does not give them a 64-bit compatibility verdict.
Compressed libraries are exempt from the ZIP offset check because that check
concerns direct loading. Stored libraries are checked conservatively for direct
loading; the tool does not decode `extractNativeLibs` from the binary manifest.

The synthetic fixtures cover little/big-endian ELF32/ELF64, malformed ranges and
headers, every load segment, distinct ZIP/ELF failures, native CRC
corruption, duplicate ZIP members, ABI mismatches, and CLI exit codes. RELRO
fixtures also cover page-boundary bytes, padded ranges, writable prefixes and
tails, neighboring LOAD segments, multiple RELRO declarations, and the
numerical examples in the Android 16 KiB guidance. Synthetic
ELF containers do not execute native code. Public CI uses these synthetic inputs
only; do not commit APKs, extracted libraries, signing material, or private code.

## Release acceptance

1. Audit the exact final APKs and retain their SHA-256 identities with the report.
2. If a library fails ELF alignment, ask its source owner to update/rebuild that
   dependency with the appropriate NDK/linker settings. ZIP realignment does not
   repair its ELF program headers. A private licensing dependency must be rebuilt
   by its authorized owner; this public-source checker does not replace it.
3. Verify final APK signatures, compiled resource tables, install/upgrade paths,
   and both 4 KiB and 16 KiB device behavior separately, using the original signing
   configuration and authorized private modules. Test whichever feature loads
   each native library, including audio conversion if applicable.

The user-supplied WaEnhancerX 2.0.3 debug/release samples were observed to contain
4 KiB `PT_LOAD` alignment in their 64-bit `libopuscodec.so` files while their ZIP
offsets were 16 KiB aligned. This explains a concrete 16 KiB packaging gap, not
the cause of message sending, status, or release-only feature reports. It does
not establish that a later build contains the same library.

Primary specification and Android guidance:

- [Android: support 16 KB page sizes](https://developer.android.com/guide/practices/page-sizes)
- [ELF program headers](https://gabi.xinuos.com/elf/07-pheader.html)
- [AOSP linker page rounding and RELRO protection](https://android.googlesource.com/platform/bionic/+/refs/heads/main/linker/linker_phdr.cpp)

The scope includes `PT_LOAD`, native ZIP alignment, and the overlap between
16 KiB-rounded GNU_RELRO protection and writable LOAD bytes outside declared
RELRO ranges. Both page edges and neighboring LOADs are considered; a raw
RELRO end modulus alone is not a sufficient failure test. Padded RELRO memory
may extend past its LOAD without causing a finding. Section tables,
relocations, symbols, full memory mapping, Android compat-mode behavior and
Android linker execution remain outside this checker. A passing result does not authenticate an APK, prove correct
resources, or certify WhatsApp/LSPosed feature compatibility.
