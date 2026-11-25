# Isolated waexdiag JNI constant probe — reconstructed V2

This candidate builds one neutral, test-only APK and tests only loading the reviewed
x86_64 libwaexdiag and returning its 14 constants: 12 strings and two arrays of
3 and 23 strings, for 38 string comparisons. It never executes a returned command
or opens a returned filesystem path. It has no permissions, account data,
production signing key, WhatsApp, LSPosed, HMA or private licensing dependency.

## Source identity and reconstruction

The C source is the exact 9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d blob, SHA256
96647f2fb72535da9a01c49d176d2ed868f93794a172c032a5afc92ea67b5756.
The candidate CMake is SHA256
fed223aeac6d9efa008b04313e2e7a3dbe983c64becd53d5318f0093d875f7ef.
The checked-in oracle is 4214 bytes, SHA256
8b041fd2e053d87da39a76ad3a55f3077f5ff6441ce346fa66c8cc2811faba9f.

Scratch became unavailable before the previous nine-file candidate was copied to
the PC. These sources are a newly reviewed reconstruction, not a claim that the
previous full manifest survived. The oracle alone was regenerated from the pinned
C and matches its previously observed exact SHA256. New receipts use V2 schemas.

## Build

Run on the lab branch in a disposable Ubuntu runner with the already accepted
standard Android SDK license, the preflight JDK17, platform36 and build-tools36.0.0:

```sh
python3 lab/qa/test_native_constants_probe.py
python3 lab/qa/build_native_constants_probe.py --audit-repo audit-source --out "$RUNNER_TEMP/native-probe-build"
```

The audit checkout must be 1c50db163ee1b8127288ea27a055242c9899541f.
The builder imports two already reviewed, SHA-pinned lab helpers. It reads the
official SDK metadata and existing acceptance registry without writing acceptance.
It acquires the pinned NDK27.0.12077973 and CMake3.22.1 packages, 686266565 compressed
bytes in total, enforcing the existing 20GiB reserve before and during acquisition
and extraction. It builds only one x86_64/API24 candidate ELF, not the four static
controls previously run.

The compiler path, target, one C input, both 16384 linker flags, LOAD/RELRO layout
and exact 14 exported JNI symbols must agree. The APK contains only that native
library, stored without compression and aligned to 16384 bytes before signing.
The ephemeral QA key is removed in finally; it must never enter an artifact.
Only the final APK, build-result.json and report logs are intended for transfer.
The native build directory, downloaded tool archives and signing material are not.

## AAPT2 minimum SDK field

The host parser accepts exactly one of sdkVersion:'24' and minSdkVersion:'24',
with targetSdkVersion:'36', the exact package and x86_64 ABI, and no permissions.
Duplicate aliases, conflicting values, wrong package/ABI or additional permission
fields fail. The observed field name is recorded in the build receipt.

The real existing Windows SQLite badging log used minSdkVersion:'24' (572 bytes,
SHA256 062b8b4f8ad66d25d8946c06968956cf483be5f9d094f2d3a64f9f6096be846f).
AOSP releasetools at commit76dde03b0152458cd101b865b517834682f2fbad,
tools/releasetools/common.py GetMinSdkVersion, recognizes sdkVersion in AAPT2 output:
https://android.googlesource.com/platform/build/+/76dde03b0152458cd101b865b517834682f2fbad/tools/releasetools/common.py
No Linux badging result for this candidate is claimed before its real build.

## Runtime and ownership

A separate AVD controller owns boot, serial emulator-5580, a fresh disposable
userdata image, exact API/minor/ABI/image identity and the expected application
page size. This launcher does not create, select, reboot or wipe any device.
It rejects another serial and an initially present probe package.

The package is org.lab.waex.qa.nativeconstants, min24/target36, testOnly and
non-debuggable. Installation uses -t without -r. The installed base.apk is pulled
and SHA256-compared before instrumentation. A fresh 32-hex nonce binds the receipt.
Success requires one instrumentation finish -1, no failure markers, every identity
field, all 14 returned values and all 38 strings. Cleanup again verifies the
installed APK hash before uninstalling only the package it introduced and checks
absence. Ambiguous installation remains failure even if owned cleanup succeeds;
unverified APK identity prevents uninstall.

Both 4K and ps16K rows must consume the exact same APK and SHA. Os.sysconf reports
application_page_size_bytes. In x86_64 ps16K images this is the application-facing
16K environment; it does not prove a native16K kernel. This probe has no SQLite
page-size claim and proves nothing about other ELF libraries or the full product.

## Verification limits

Host tests use only Python temporary files and a simulated ADB transport. Their
APK-shaped fixtures are structural controls, not Android-installable artifacts.
They cover both SDK field aliases, manifest restrictions, duplicate/invalid JSON,
all returned constants, wrong page/API/identity, install ownership, unique finish
and nonce, installed hashes and cleanup. These checks do not substitute for the
real Linux build, Android loader or ART/JNI observations. A build PASS is explicitly
PASS_BUILD_ONLY; runtime PASS additionally requires verified uninstall.
