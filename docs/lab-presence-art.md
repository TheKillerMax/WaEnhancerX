# ART presence laboratory on Android 7.0, 7.1 and 8.0

This isolated fork workflow builds one small public QA APK and installs those
same verified bytes in three fresh x86_64 AVDs: API24, API25 and API26. It follows
the two successful empty-AVD pilot receipts from run45526368865. The shared
matrix lock, official image identities, existing license acceptance, KVM,
Android API/minor/ABI/page-size checks and owned-process cleanup remain required.

## Purpose and acceptance

The Robolectric matrix recorded four graphic assertion failures on API24/25.
The neutral Canvas control reproduced failures without WAEX. Those results
remain failures; they are not overwritten by the separate ART result.

The published V3 probe preserves both original renderer pixel cases and all
four assertion strings. It adds a neutral circle and a plain Android view case.
Each ART job must execute all four cases, pass all four, omit none and preserve
seven PNG observations. The host requires the same nonce in the final JSON and
Instrumentation Bundle, exactly one successful finish code, installed APK hash
equality and verified removal of only the owned QA package. A missing or partial
receipt cannot be a PASS. The callback runs only after the owned AVD boot gate.

This tests extracted renderer behavior with four complete supporting Java
classes. It does not install the complete WAEX product or claim Xposed hook
discovery, LSPosed, WhatsApp, provider authorization, DSU or physical ARM64
coverage. All three ART rows expose 4096-byte application pages. Separate
SQLite and JNI probes have their own evidence and acceptance criteria.

## Immutable build inputs

The source/oracles are checked out at
c52f064bad7ba32445f8515bc2f0421618438975. Seven exact LF source hashes are pinned.
The eight V3 files originated at
c2fd668da20f8620112d649b34224559cab30942. The launcher and its host controls now
have a reviewed API24 readback/cleanup delta. The offline builder and its README
now describe the fixed compiler closure; the remaining four probe files retain
their original hashes. The lock records that origin separately. Each new build
records probe_revision as its actual workflow commit, verifies the laboratory
Git HEAD against that commit and checks all eight current file hashes. These
new bytes are not attributed to the unchanged c2fd revision. The positive extracted renderer harness
must retain SHA256
241385367b8ff949679f330c5632245e4eb8e3a6b1b191074b7d2313fd1cf63a.

The Linux builder prepares Kotlin 2.0.20 from the unchanged ClassValue toolchain
helper and lock, whose two source hashes are pinned in the Presence lock. The
compiler home contains exactly nine Maven Central JARs with fixed sizes and
SHA256 hashes, including stdlib 2.0.20 and the compiler's reflect 1.6.10 dependency.
The compiler runs with an explicit classpath. Runner Kotlin installations and
bundled compiler plugins are not selected. The builder uses the runner's existing
JDK21, SDK platform36 and build tools36.0.0, recording actual tool/JAR hashes.
JAVA_HOME and PATH refer to that same JDK; inherited Java/Kotlin option variables
are cleared. The offline build keeps ActiveProcessorCount=2 as explicit JVM
arguments. The JDK patch and its native java/javac identity are observed and
recorded; equal APK bytes across JDK patches are not promised. It does not
alter the default JDK17 environment of boot jobs, because that Java binary is
part of the successful preflight identity. It does not invoke project Gradle,
use private modules, accept licenses, install SDK components or use a production
signing key. The temporary QA key is removed in finally.

In addition to the nine compiler inputs, junit4.13.2 and hamcrest-core1.3 are
acquired:429605 bytes total for these two test dependencies. Each gets
one request to its pinned canonical Maven Central URL, with exact size and
SHA1/SHA256/SHA512 checks. A redirect or HTTP429 stops the build without retry.
The official sidecars provide SHA1. SHA256 and SHA512 were computed from bytes
whose size and SHA1 matched those official records; their official SHA512
sidecars returned404. The lock records that distinction.

Both raw D8 output streams must be empty. Any diagnostic, whitespace or binary
byte blocks the build; no warning patterns are filtered. Reports retain separate
stdout/stderr files and their exact lengths and hashes, the nine compiler input
pins, Kotlin/JDK versions and the helper/lock identities. The artifact consumer
requires the same workflow commit, run ID and attempt, current builder and lock,
the qualified compiler receipt and the empty D8 receipt before boot.

## Artifacts and execution

The successful build publishes one APK plus its provenance manifest. The build
job separately hashes the APK and exposes that digest as a job output. Each
boot job requires agreement with that output, the manifest, source/probe/lock
identities and its own workflow commit before installation.

The shared boot controller creates one AVD per job, uses only emulator-5580,
has no TCG fallback and reaps its owned process in finally. At most two ART
jobs run simultaneously. Installation is test-only, without replacement, and
the package must initially be absent. Readback copies matching the built QA
APK are removed from reports after their identities are recorded. A mismatched
readback is preserved outside uploaded reports and causes failure.

The observed API24 adb pull failure has a narrow alternate transport: only
return code 1, empty stdout, the exact recorded remote-object diagnostic and
/data/app/org.waex.qa.presence.host-<validated suffix>/base.apk, with no partial
destination, permit exec-out /system/bin/cat. Its bytes are captured without
text conversion, with a 60-second capture deadline and an observed 8 MiB output bound;
stderr is bounded separately. A killed capture child has up to five additional
seconds to be reaped; this is not a 60-second bound for the whole launcher. Acceptance still requires the producer's exact
length (at most 2 MiB) and SHA256. Other APIs, diagnostics, paths, partial copies,
timeouts and size/hash mismatches remain failures. The shared controller has
already verified the API24 row's 4096-byte application page size.

Every uninstall requires a new package-path query and matching complete
readback, including after an install that reported Success. An unknown or
mismatched current APK is not removed. This corrects the former host fixture
expectation that confirmed installation alone justified removing a mismatched
APK. No root, permission/SELinux changes or alternate device selection occur.

Reports contain bounded logs, JSON receipts, PNG files and manifests. The APK
artifact is separate; keys, SDKs, images, private partitions and caches are
never uploaded. Build success means PASS_BUILD_ONLY; it is not an ART PASS.
The per-row final receipt is presence-art-lab-result.json.

## Host checks and current state

Run python3 qa/test_presence_art_lab.py for six host control groups. They cover
all JAR checksums, one-request behavior, HTTP429, source mutations, complete
ART receipts and artifact provenance. Synthetic inputs are explicitly not
Android APKs or an Android execution. The launcher retains all eighteen original host scenarios, with the
installed_mismatch cleanup expectation corrected explicitly, and adds literal
API24/path/error guards, both readback identities and binary size/time controls.
Run python3 qa/test_presence_art_toolchain.py for eleven additional control groups
covering the closed compiler recipe, changed or extra JARs, injected environment
options, compiler/JDK receipts, raw D8 output, separate command logs and deadlines.
All three suites run normally and with PYTHONOPTIMIZE=1 before build acquisition
in CI, preserving their outputs even when a control fails. Host controls remain synthetic;
actual Android results must be obtained separately.

This wrapper was reconstructed as a new reviewed version after the scratch
executor disconnected. No earlier wrapper's host PASS is attributed to these
new bytes. The published V3 source pins and earlier pilot evidence remain
independently available on the Windows host. Real Linux build and ART outcomes
must be recorded from this workflow's run before reporting execution success.

## Technical references

- https://developer.android.com/studio/test/command-line
- https://developer.android.com/reference/android/app/Instrumentation
- https://developer.android.com/tools/apksigner
- https://developer.android.com/tools/zipalign
- https://central.sonatype.org/faq/429-error/

The normal/default repository workflows, source runner defaults, pixel
expectations and production compatibility declarations remain unchanged.
Protected workflow changes are an isolated laboratory proposal and still
require the repository's maintainer review before any nightly integration.
