# Diagnostic ELF comparison with the project's exact NDK

This isolated lab compares the original CMake build against the reviewed two-flag
candidate, using NDK `27.0.12077973` and CMake `3.22.1`. It builds `waex_diag.c`
for `arm64-v8a` and `x86_64`, both targeting Android API24. Only ARM64 is a
production ABI for this source in the recorded project; x86_64 is a lab control.
The earlier six NDK28 compiler controls are separate evidence and are not rerun.

Publish this job on `lab/android-emulator-matrix-nightly8-20261124` after reviewing
the real Linux preflight and merging its corrected `sdk_license_hash` helper.
The workflow starts on a change to its own four executable/fixture files and also
declares a manual trigger. The repository, branch and public visibility are
checked in both the workflow and Python. The job uses the standard Ubuntu24.04
runner, read-only repository permissions, immutable action pins and a 25-minute
limit. It requests no Windows resources or device access.

## Frozen inputs

`waex_diag.c` is the unchanged source from base commit
`9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d`, SHA256
`96647f2fb72535da9a01c49d176d2ed868f93794a172c032a5afc92ea67b5756`.
The original CMake file has SHA256
`b71381b25d68897a2f881df9809e5a10e5d8f75fc76037c2b2a2277b5ffed9be`.
The candidate fixture is byte-for-byte the reviewed CMake file, SHA256
`fed223aeac6d9efa008b04313e2e7a3dbe983c64becd53d5318f0093d875f7ef`.
It adds `-Wl,-z,max-page-size=16384` and `-Wl,-z,common-page-size=16384`.

The already published ELF auditor and unchanged source baseline are read through
a sparse checkout of commit `1c50db163ee1b8127288ea27a055242c9899541f`.
The auditor must match SHA256
`e9d840a160943cf10cd766977a341e256a1815a0e87f5a9cb89bb31d2094faa1`.
The lab imports its existing ELF/RELRO parser and independently contrasts every
LOAD and GNU_RELRO field against the exact NDK's `llvm-readelf` output.
It does not duplicate the auditor or edit any checked-out product source.

## Official tools and existing license

| Package | Official archive | Bytes | Published SHA1 pin |
|---|---|---:|---|
| NDK27.0.12077973 | `android-ndk-r27-linux.zip` |663,957,918|`5e5cd517bdb98d7e0faf2c494a3041291e71bdcc`|
| CMake3.22.1 | `cmake-3.22.1-linux.zip` |22,308,647|`fd0a48b4a758310df8c7aa51f59840ed48fe7ed8`|

The checksum-pinned Android SDK CMake package reports the exact banner
`cmake version 3.22.1-g37088a8`. The runner checks that full build identity;
the package revision and project CMake requirement remain `3.22.1`.

Both URLs are fixed under `https://dl.google.com/android/repository/`. The job
rechecks their exact package path, revision, Linux archive, size and checksum
against official repository metadata before downloading 686,266,565 bytes total.
Redirects, changed pins and new terms produce `BLOCKED`. SHA256 identities of
the actual downloads are recorded in addition to the published SHA1 checks.
Archive expansion is measured before extraction and 20 GiB of disk remains
reserved throughout. All tool files stay in the disposable runner work directory.
The installed SDK is not changed.

The metadata's license text is passed through the reviewed SDK JAXB normalization
before comparing its SHA1 with the existing `android-sdk-license` registry.
The required identity is `24333f8a63b6825ea9c5514f83c2829b004d1fee`, the SDK2019
terms already registered on the actual runner. No license is accepted, copied or
written by the job; the registry is compared before and after the operation.

## Oracles and result

Each CMake invocation uses the NDK's supported Android toolchain file, a separate
build directory, API24 and a fixed ABI. The compile database must contain exactly
the diagnostic source, clang from the verified NDK and the correct compiler target. The candidate's verbose
linker invocation must contain both reviewed alignment flags.

`PASS_NATIVE_STATIC` requires all four builds, the expected ELF class/machine,
GNU_RELRO presence, exact agreement with `llvm-readelf`, and the same 14 named JNI
exports with global/default function binding. It also requires the original NDK27
build to reproduce the below-16KiB LOAD alignment gap, while both candidate builds
have no LOAD or RELRO overlap findings. A missing baseline failure is reported as
blocked/inconclusive instead of being used to attribute a fix.

Only bounded JSON/text build receipts, readelf output, compile commands, version
logs and hashes are uploaded with one-day retention. No tool archive, compiled
ELF, APK, signing key, image or complete license text is uploaded.

This result concerns native compilation and static ELF structure. It does not
execute JNI, boot Android, inspect APK ZIP alignment, validate the full WAEX app,
read private `waexlic`, or establish anything about `opuscodec` or other libraries.
The app's runtime behavior in 4 KiB/16 KiB environments remains a separate test.

## Primary documentation

- [Android guidance for NDK27 and the two linker flags](https://developer.android.com/guide/practices/page-sizes)
- [Supported NDK CMake toolchain and explicit API/ABI arguments](https://developer.android.com/ndk/guides/cmake)
- [Official SDK archive metadata](https://dl.google.com/android/repository/repository2-1.xml)
- [The SDK's JAXB license adapter source](https://android.googlesource.com/platform/tools/base/+/studio-2023.1.1/repository/src/main/java/com/android/repository/impl/meta/TrimStringAdapter.java)
