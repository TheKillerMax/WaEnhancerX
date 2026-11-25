# Extended Android emulator laboratory: 21 targets and neutral SQLite

## Scope and current evidence

This experiment belongs only to the public fork branch
`lab/android-emulator-matrix-nightly8-20261124`.
It does not change the product, its SDK levels, the default branch, upstream CI,
Windows virtualization, a phone, or personal application data. Workflow changes
remain a separate laboratory review under the project's R5 boundary.

The reviewed [preflight run 45520358898](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/45520358898)
at commit `9067ca002f8b687fb9ac61fee1b8c5ac116fb3cb` passed.
The corrected [pilot run 45526368865](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/45526368865)
at commit `2bce24e4310add9318c83fc5922bb425e71a1f53` passed both targets.
The API 24 guest booted in 21.022 seconds and exposed 4096-byte application pages;
the API 35 simulated 16 KiB guest booted in 31.093 seconds and returned 16384
through getconf. Both owned emulator processes were reaped, license files were
unchanged, and neither pilot installed an APK. All 143 manifest members in the
two artifacts were verified. Earlier failed runs retain their BLOCKED results.

The matrix lock binds those receipts, the complete reviewed catalog identities,
source hashes, existing tools, and build SDK metadata. A ready lock authorizes
the proposed experiment; it does not claim an expanded boot or SQLite PASS.
No execution of the 21-target matrix is implied by the two pilot successes.


## First complete matrix run and the next experiment

[Run 45532867332](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/45532867332)
at commit a744a9d2982fe3dfb3ee5f7eb904caf513e732c7 completed with 24 artifacts.
All artifact hashes were checked against the browser receipts. Fourteen rows
passed: APIs 25-36 plus the API 35/API 36 simulated 16 KiB rows. Seven stayed
BLOCKED: API 24, both 36.1 rows and all four 37.x rows. The original build ran
22 Linux host controls and produced one 16785-byte APK with SHA-256
56fc775204059304ffbce7ebb32e3ee8ad9b204a660cc18bd0556222f0185d1b.

API 24 failed installed-APK readback before instrumentation. Four modern rows
observed a missing package service after sys.boot_completed; API 36.1 also
reported a broken pipe during install. API 37 and 37.1-16k reached instrumentation
but could not open their own database because the cache directory did not exist;
both verified removal afterward. These are distinct observed failures, without
a demonstrated common cause. No SQLite oracle failure or RAM/SELinux cause is
inferred from those messages.

For API 36 and later, the next controller waits for package access, user 0 state
RUNNING_UNLOCKED and one unchanged system_server PID before and after each
sample. At least three matching observations must span 15 seconds. This remains
inside the original 420-second total boot budget; failed samples or a changed PID
reset that observation window. It is a bounded precondition, not a guarantee
against later service crashes. No installation is retried.

AOSP Android 16 sets sys.boot_completed before allowing user unlocking through
UserController.onBootComplete. The prior flag alone therefore did not establish
credential-encrypted storage readiness. Existing artifacts do not contain guest
logcat, user state, PID history or guest disk usage, so they cannot distinguish
CE delay, system_server restart or resource failure conclusively. The probe
already calls Context.getCacheDir, which attempts directory creation; its SQL
and 280 checks remain unchanged.

Before terminating a modern owned AVD, the controller now attempts bounded crash,
system and events logcat snapshots, user/PID, memory, /data space and properties.
Diagnostic acquisition has a 45-second budget; each command gets at most 6 seconds.
The final child shutdown can add 20 seconds plus 0.5-second polling: up to 65.5
seconds of declared waits, with the job timeout still enforced. Logs retain the
8 MiB bound. The total boot acquisition budget is 420 seconds; a late sample is
rejected even if command shutdown takes additional time. Diagnostic failures are
recorded separately and cannot replace the original failure or prevent owned
emulator cleanup. RAM 2048 MiB, two CPU cores and the inherited heap setting are
unchanged. The same callback, catalog and APK producer contract remain in use.

These changes are candidates for a new complete 21-row run at one commit. The
first run retains its original source pins, 22 controls and BLOCKED result.


## Exact selected catalog

Each row has its own fresh runner and AVD. There are 15 normal rows and six
simulated 16 KiB rows. Stable image metadata and an already accepted SDK license
are required. AOSP default images at APIs 27, 31 and 32 make no GMS claim.

| Target | Package version | Image tag | App page bytes |
| --- | --- | --- | ---: |
| api24 | android-24 | google_apis | 4096 |
| api25 | android-25 | google_apis | 4096 |
| api26 | android-26 | google_apis | 4096 |
| api27 | android-27 | default | 4096 |
| api28 | android-28 | google_apis | 4096 |
| api29 | android-29 | google_apis | 4096 |
| api30 | android-30 | google_apis | 4096 |
| api31 | android-31 | default | 4096 |
| api32 | android-32 | default | 4096 |
| api33 | android-33 | google_apis | 4096 |
| api34 | android-34 | google_apis | 4096 |
| api35 | android-35 | google_apis | 4096 |
| api36 | android-36 | google_apis | 4096 |
| api36.1 | android-36.1 | google_apis | 4096 |
| api37 | android-37.0 | google_apis | 4096 |
| api35-16k | android-35 | google_apis_ps16k | 16384 |
| api36-16k | android-36 | google_apis_ps16k | 16384 |
| api36.1-16k | android-36.1 | google_apis_ps16k | 16384 |
| api37-16k | android-37.0 | google_apis_ps16k | 16384 |
| api37.1-16k | android-37.1 | google_apis_ps16k | 16384 |
| api37.2-16k | android-37.2 | google_apis_ps16k | 16384 |

All targets use x86_64. Google documents that these x86_64 images simulate 16 KiB
application behavior while the kernel remains 4 KiB. They do not establish
compatibility on real ARM64 hardware. The application page size and SQLite's
PRAGMA database page size are separate fields and are never equated.

## Execution and resource limits

The workflow builds a neutral instrumentation APK once from the six reviewed
SQLite sources, using the already installed SDK platform 36, build-tools
36.0.0 and the reviewed Java runtime. The build uses an ephemeral QA signing key,
removes it, records source/tool/SDK hashes, and produces PASS_BUILD_ONLY.
Every target downloads the same artifact and verifies its SHA-256 and the
producer receipt before doing any SDK or AVD work.

The standard public ubuntu-24.04 runner is selected, with at most two target jobs
in parallel. No paid runner or secrets are configured. The builder has a
10-minute limit; each target has 25 minutes, a 420-second boot limit and a
240-second instrumentation limit. Each target requires at least 16 GiB free
before installing its one image and retains the controller's 2 GiB reserve.
No SDK image, userdata image, signing key or memory dump is uploaded.

Every fresh target job executes the reviewed bootstrap: a KVM ACL entry scoped
to the ephemeral runner UID, the pinned official emulator, and the pinned
Ubuntu libpulse dependency. Java remains the runner's reviewed default for SDK
tools and boot. No SDK license is accepted, no software CPU fallback is enabled,
and installed tool/source identities must match the lock. Artifacts are kept
for one day and include complete reports on failure.

The workflow triggers only on its own file or matrix lock changes in the lab
branch, or explicit workflow dispatch. Its permission is contents:read.
The final job runs even when a target fails and reports every missing or blocked
row. Only 21 distinct, current-run, complete PASS receipts permit
PASS_21_NEUTRAL_SQLITE_TARGETS_ONLY.

## Version and page-size identity

For API 36 and later the controller reads ro.build.version.sdk_full and checks
its major and minor components against the selected repository metadata.
AOSP represents this property as text such as 36.1 or 37.2. The numeric value
corresponding to SDK_INT_FULL is major * 100000 + minor: 36.1 becomes 3600001.
The report distinguishes that derivation from reading the Java field, which it
does not do. A missing, malformed, out-of-bounds or mismatched property blocks
the row. API release text alone cannot prove a minor version.

For APIs 24-28 only, the page-size reader may use the legacy Bionic AUXV route
when getconf exits 127 with a recognized missing-command message and a separate
shell check confirms no /system/bin/getconf file, symlink or command resolution.
It also requires x86_64 and a reviewed 4096-byte target. The controller reads
the actual /system/bin/cat executable through adb exec-out, retains its ELF
header and complete-file hash, then reads that cat process's /proc/self/auxv.
It requires ELF64 little endian, machine x86-64, 8-byte pointers, complete
tag/value pairs, one final AT_NULL and exactly one AT_PAGESZ of 4096.
Truncated records, duplicate tags and a 16384 value are rejected.

This fallback is unavailable on API 29 and later and on every ps16k image.
The ps16k boot gate requires the app-facing getconf result of 16384.
The SQLite APK independently calls Os.sysconf inside its own process.
AUXV's kernel page size is never used to assert simulated 16 KiB behavior.

## SQLite identity, oracles and cleanup

The package is org.lab.waex.qa.sqlite, minSdk 24, targetSdk 36 and testOnly.
It has no Activity, permissions or native libraries. The instrumentation uses
only its own synthetic database with 50,000, 100,000 and 150,000 row workloads,
portable scalar lexicographic predicates and 280 fixed checks. Its own database
must be absent at completion. A fresh random nonce, exact API, x86_64 process
and application page size bind each instrumentation receipt to that execution.

The controller refuses a preexisting probe package, installs without replacement,
pulls the single installed base APK and verifies its hash. Immediately before
uninstall, it reads and verifies that installed hash again. A different package
binary is never removed. Ambiguous installation and cleanup failures remain
BLOCKED; an acknowledged uninstall and verified absence are required for PASS.
Only verified temporary read-back APK copies are deleted.

For API 24 with 4096-byte pages only, a pull with the exact observed missing-object
message and exit 1 may be followed by binary exec-out cat of the validated
/data/app path of this package. Transport failures, partial pull files, additional
error output, other SDKs and other page sizes do not permit that fallback.
The expected producer APK must be at most 2 MiB; the read-back must match its exact
size and SHA-256 before instrumentation and again before uninstall. The original
8 MiB transfer bound and 60-second deadline remain. No PTY, root or policy change
is used. This adaptation does not classify the original errno or SELinux cause.

The final summary rechecks every file manifest, GitHub run/attempt/commit,
controller and lock hash, bootstrap result, the single producer APK and receipt,
guest major/minor identity, instrumentation transcript and all validator oracles.
An omitted, duplicate, foreign-run, altered or failed target cannot be hidden
by other successful targets. Timing samples are descriptive fixture output;
no application performance improvement is claimed.

## Shared controller hook

The controller exports BootContext and main(argv=None, *, targets=None,
read_lock=checked_lock, boot_action=None, phase='boot_pilot_only',
result_name='pilot-result.json', limits=DEFAULT_LIMITS). BootContext carries
target, api, minor, application_page_size_bytes, adb, serial, env, work, out,
guest, entry and the mutable result dictionary. The post-boot callback receives
this context only after the identity gates and must return a complete dictionary
with status PASS. The controller owns emulator cleanup in its finally block.

The matrix module exports TARGETS and checked_lock without running ADB on import.
ART presence can select only api24/api25/api26 through that contract, write its
own receipts and PNG files under out/presence-art, and use its own phase and
result filename. Recursive manifests cover that evidence. SQLite, ART and JNI
results remain distinct; the SQLite workflow does not execute the other probes.

## Host verification and runtime limits

The page-reader controls cover malformed ELF/AUXV data, tool-presence ambiguity,
legacy platform boundaries, and the prohibition of a 16 KiB fallback. Matrix
controls cover SDK full-version parsing, complete target enumeration, recursive
manifest integrity, producer contracts, installation ambiguity, wrong installed
APK hashes, stale nonces and cleanup failure. ADB in those lifecycle controls is
simulated; the controls are not Android runtime evidence.

Run the controls on Linux with the reviewed preflight module available:

    python3 qa/test_android_emulator_pilot_pages.py
    python3 qa/test_android_emulator_matrix.py
    python3 qa/test_android_sqlite_probe.py

The current host suites contain 14 page/readiness controls, 9 matrix controls and
7 SQLite controls. On Windows, 29 pass and the original Linux AUXV comparison is
explicitly skipped; the existing workflow must run all 30 on Linux before build.
The readiness controls model missing services, locked users, changed PIDs,
deadlines and incomplete diagnostic collection. They are simulated host evidence.

The first matrix run established its Linux producer and 14 successful SQLite
rows, with 7 blocked rows. Complete 21-row acceptance requires a new common run
and commit; successes from different runs are not combined. ART presence and
JNI loading remain separate experiments with their own receipts.

## Primary references

- [AOSP Android 16 Build.java: SDK_INT_FULL property contract](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-16.0.0_r4/core/java/android/os/Build.java)
- [Android VERSION_CODES_FULL constants](https://developer.android.com/reference/android/os/Build.VERSION_CODES_FULL)
- [AOSP shell utility availability by release](https://android.googlesource.com/platform/system/core/+/refs/heads/main/shell_and_utilities/README.md)
- [Nougat Bionic sysconf implementation](https://android.googlesource.com/platform/bionic.git/+/nougat-release/libc/bionic/sysconf.cpp)
- [Oreo Bionic sysconf implementation](https://android.googlesource.com/platform/bionic/+/refs/heads/oreo-r6-release/libc/bionic/sysconf.cpp)
- [Pie Bionic sysconf implementation](https://android.googlesource.com/platform/bionic/+/refs/heads/pie-qpr1-s2-release/libc/bionic/sysconf.cpp)
- [Google's x86_64 16 KiB simulation explanation](https://android-developers.googleblog.com/2024/08/adding-16-kb-page-size-to-android.html)
- [GitHub Linux runner KVM announcement](https://github.blog/changelog/2024-02-22-github-hosted-runners-linux-x64-runners-now-support-hardware-acceleration-for-android-emulators/)
- [GitHub hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

- [AOSP Android 16 boot-completed ordering](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/services/core/java/com/android/server/am/ActivityManagerService.java)
- [AOSP Android 16 user unlock transition](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/services/core/java/com/android/server/am/UserController.java)
- [AOSP Android 16 get-started-user-state command](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/services/core/java/com/android/server/am/ActivityManagerShellCommand.java)
- [AOSP credential-encrypted storage availability](https://source.android.com/docs/security/features/encryption/file-based)
