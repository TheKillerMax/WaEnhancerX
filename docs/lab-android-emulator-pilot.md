# Isolated Android boot pilot

Status: prepared for the first boot pilot after the verified successful
[preflight run 45520358898](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/45520358898),
commit `9067ca002f8b687fb9ac61fee1b8c5ac116fb3cb`. Its bootstrap and preflight
both passed, including the library loader, pinned emulator version/build, KVM and
existing license acceptance. The lock is now `ready: true` and binds their exact
report and tool identities. No Android image has booted during that preflight.

The pilot adds two independent, sequential matrix entries on public standard
`ubuntu-24.04` runners: API 24 Google APIs x86_64 and API 35 Google APIs x86_64
with application-facing 16 KiB page-size simulation. Each job has a 25-minute
limit, a fresh AVD and separate evidence. It does not install an APK.
Before any setup, each job validates the reviewed lock. It then runs the same
runner-specific KVM ACL and exact emulator bootstrap used by the successful
preflight; neither setup nor permissions persist between GitHub runner jobs.
The bootstrap also supplies the exact reviewed Ubuntu libpulse0 client-library
dependency and verifies its loader, emulator version/build and KVM availability.
The bootstrap receipt is retained alongside that target's boot reports.

## Required evidence before enabling

The lock records the successful preflight run URL and exact commit, SHA-256 of
`preflight-result.json`, `catalog.json`, `tool-identities.json` and
`installed-component-properties.json`, and the measured SDK manager, emulator,
ADB and Java hashes. Image identities come from that actual catalog, and the
observed runner free space exceeds the 12 GiB allowance for each target.
A successful bootstrap receipt, including
confirmed libpulse loading, is also required. The checkout's preflight and
bootstrap source hashes must match the reviewed lock before setup may run.
The earlier catalog proposals from run 45517438374 match the successful run's
catalog byte for byte. That earlier run remains `BLOCKED` because QEMU could not
load libpulse.so.0; no failed result is promoted to `PASS`. The two pilot targets
and the preflight's 15 selected entries do not exhaust every minor-version and
16 KiB image in the official catalog; any extension is reviewed separately.

The pilot rechecks public repository/branch, KVM, available disk, exact tool
hashes, existing license acceptance, stable image revision/archive metadata and
minimum emulator dependency before invoking the official SDK package installer.
No license input is provided. Only the selected image package may change SDK
metadata. Existing tool identities and license files must remain unchanged.
The installer manages the archive download; the report preserves the official
archive checksum and installed package metadata identities. This script does
not claim a separately measured hash of the compressed archive bytes.

Initial free disk must be at least 12 GiB; command execution and boot monitoring
preserve a 2 GiB reserve. Tool commands and the emulator have time and log-size
limits. No preinstalled SDK package is deleted to recover disk. AVD data and SDK
images stay outside the report directory and are never uploaded or cached.

## Boot acceptance and cleanup

The command requires `-accel on`; it has no software-CPU fallback. SwiftShader
must be advertised by the actual emulator. A fresh AVD requests 2 GiB userdata,
2 GiB RAM, two virtual CPUs and a 480x800 display. The emulator may enlarge
userdata to its supported minimum; available disk is monitored while it runs.

Guest queries always use `adb -s emulator-5580`. Success requires boot-complete,
the exact Android API, x86_64 ABI, the expected application-facing page size
(4096 or 16384 bytes), a responsive package manager and a still-running emulator.
The process created by this job is terminated and reaped on success or failure.
Only bounded reports are retained for one day.

On the x86_64 16 KiB image, this checks simulated application-facing behavior;
the kernel still uses 4 KiB. It does not validate a real ARM64 16 KiB device.
SQLite `PRAGMA page_size` is a different quantity and is outside this boot-only
pilot. The separately reviewed neutral SQLite probe can be added after boot
evidence is available, using one identical APK/SHA throughout the matrix.
Boot success does not establish WAEX, WhatsApp or LSPosed compatibility.

## API 24 page-size command compatibility

The first real pilot run, [45521579068](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/45521579068),
reached `sys.boot_completed=1` on API 24 after 17.006 seconds. Its subsequent
`getconf PAGE_SIZE` command returned 127 with `/system/bin/sh: getconf: not found`.
That original receipt remains `BLOCKED`. The API 35 16 KiB target passed its full
boot gate using `getconf=16384`; neither target installed an APK.

The correction permits a fallback only for that exact missing-command result,
API 24, x86_64 and a reviewed 4096-byte target. Nougat Bionic implements both
page-size `sysconf` queries through `getauxval(AT_PAGESZ)`. The job therefore reads
the first 64 bytes of `/system/bin/cat`, verifies an ELF64 little-endian x86_64
executable, then reads that exact executable's `/proc/self/auxv`. Both commands
use `adb exec-out` to avoid PTY newline conversion. Parsing requires complete
64-bit tag/value pairs, unique tags, a final `AT_NULL` and one `AT_PAGESZ=4096`.
Wrong architecture, truncated input, duplicate tags, missing values and other
command failures stay blocked. No package, binary, privilege or device setting
is installed or changed for this read.

This fallback is forbidden on the simulated 16 KiB image: its kernel AUXV can
describe 4 KiB, so only the application-facing `getconf` result satisfies that
target. The report records the observation method and raw-input hashes.

`python3 qa/test_android_emulator_pilot_pages.py` exercises the narrow fallback,
malformed inputs and refusal on API 35. Its optional Linux host AUXV comparison
is host evidence; it does not count as an Android rerun.

## Primary contracts

- [SDK package installation](https://developer.android.com/tools/sdkmanager)
- [AVD creation](https://developer.android.com/tools/avdmanager)
- [Emulator acceleration and command-line options](https://developer.android.com/studio/run/emulator-commandline)
- [Explicit ADB target selection](https://developer.android.com/tools/adb)
- [x86_64 application-facing 16 KiB simulation](https://android-developers.googleblog.com/2024/08/adding-16-kb-page-size-to-android.html)
- [Nougat Bionic sysconf](https://android.googlesource.com/platform/bionic.git/+/nougat-release/libc/bionic/sysconf.cpp),
  inspected at commit `7cdb481dfe626524c93e4b6a1aae4621b1beedbc`, blob `125b3c92fd2038c8c0caab0dae418040e9420b93`.
- [Nougat Bionic getauxval](https://android.googlesource.com/platform/bionic.git/+/nougat-release/libc/bionic/getauxval.cpp)
- [Android shell utility availability by release](https://android.googlesource.com/platform/system/core/+/refs/heads/main/shell_and_utilities/README.md)

These workflow changes remain separate from product and default-branch changes.
A future PR targeting nightly needs the separate protected-path R5 review.
