# Laboratory: decimal Android SDK images and ClassValue linkage

## Evidence and next controlled experiment

The prior matrix (45549534897, 214e4646a28c769997176def1dfb089e8258bc97) recorded repeated SurfaceFlinger RegionSampling SIGABRTs on the API 36.1 guest, including GoldfishMapper::readFromHost and Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma. The readiness horizon was not achieved and no SQLite probe installation was attempted on that guest. This is not evidence of an application failure.

A public report of the matching symptom describes incorrect decimal target serialization by older avdmanager versions: https://github.com/actions/runner-images/issues/14484 . The previous controller did not retain the AVD index, so the particular target=android-0 cause remains a hypothesis for our runner.

On fresh owned decimal-package AVDs, retain the original index and configuration. Verify the exact pinned image directory and owned AVD path. Accept the expected decimal target as-is; repair only the literal android-0 mismatch, and fail closed otherwise. Retain the before/after bytes and independent hashes. Do not change the image, GPU, memory, KVM, licensing, readiness horizon, SQLite probe, or its original 280 checks. Verify the metadata receipt during matrix aggregation. Integer package targets are unchanged.

The new ClassValue workflow compiles the full two class definitions at exact baseline/candidate commits and runs the original receipt fixture before producing separate DEX jars. It records the expected baseline linkage failure below API 34, and requires candidate initialization and cache checks, using fresh isolated AVDs on API 24/30/33/34. It is not an application installation or an Xposed, WhatsApp, real ARM64, DSU, or physical-device test. A successful host build or simulated oracle test must not be counted as ART execution.

## Validation

Local host controls retain the original checks, add byte-preservation and rejection cases, and use an import-only fcntl sentinel on Windows. The Linux runtime matrix and the ClassValue runtime workflow remain the independent acceptance tests. Review results by their exact commit and attempt; never merge rows from different commits.

### Follow-up: ClassValue source identity

The initial Linux build (45553277154) rejected HideReceiptsHook.java before compilation. The reviewed Windows baseline bytes use CRLF; independent Code UI readback of the exact baseline commit plus its final LF matches the derived LF SHA-256. Retain every original reviewed SHA-256 and pin both complete byte representations, generated from the reviewed bytes. Reject changed content, mixed line endings, BOM, added or removed final newline, and unpinned hashes. Compile the actual exact-commit checkout without rewriting it; record every observed raw SHA-256 and require the original fixture receipts to agree with those actual raw hashes. The runtime validator checks the full observed checkout hash map against these precomputed pins. No linkage result has yet been claimed.

### Follow-up: API 24 binary identity

Run 45553715026 at 2ddf9d449bda1e329e1bcad13a49083249adbb1a completed the build and ART probes on API 30, 33 and 34. API 24 booted, but the guest returned exit 127 and `/system/bin/sh: sha256sum: not found` during the initial JAR identity check. It never executed either ART variant. The cleanup identity check also failed, so the probe refused to remove the unverified file and the controller reaped the owned disposable emulator. This is a lab utility dependency, not a ClassValue failure.

Read each owned JAR afresh with `adb exec-out /system/bin/cat`, retaining the original owned ADB server environment. Compare raw binary size and SHA-256 on the host against the single producer before execution and again before removal. Reject unexpected paths, incomplete or altered bytes, nonzero exit codes, stderr, excessive output and timeouts. Require a new receipt for each read and close stdin; reap a timed-out child. The readback payload is temporary, while each command, size, hash and failure remains in the runtime evidence. The exact producer JARs remain in the build artifact. Record initial and cleanup failures separately. The four-environment rerun remains the acceptance gate; prior PASS rows are not carried forward.

### Follow-up: fixed Kotlin compiler inputs and D8 diagnostics

Run 45555512200 at ed5020e508c733952af2fb80c505119abf256b23 completed the four ART rows: 90 checks, eight fresh nonces and 24 binary identity receipts, with verified cleanup. Its build still emitted 952 Kotlin metadata parsing warnings and 953 rewriting failures per variant. The compiler was 2.4.21 under inherited JRE 17; D8 reported metadata 2.4.0 above its supported 2.2.0. These narrow runtime observations do not qualify the compiler toolchain for general metadata behavior.

Construct a closed Kotlin home from nine Maven Central artifacts with fixed URL, byte length and SHA256, using compiler and stdlib 2.0.20. Keep the original production sources, Main.java, receipt runner, fixture and source lock unchanged. The official D8/R8 compatibility table lists 8.5.10 as the minimum R8 version for Kotlin 2.0: https://developer.android.com/build/kotlin-support . The compiler dependency declaration is retained at https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-compiler/2.0.20/kotlin-compiler-2.0.20.pom .

Select the same preinstalled JDK 21 for JAVA_HOME, PATH and explicit Java commands; verify actual Java and javac versions, runtime home and hashes of the launcher, modules, JVM and API profiles. Record the patch version instead of claiming binary reproducibility across different JDK patches. Reject an incomplete JDK, a changed dependency, any extra compiler-home file, or a different compiler/JRE version. Recheck the toolchain after the build. Do not load other distributions or bundled compiler plugins.

Reject every nonempty D8 stdout or stderr stream after a successful process exit, preserving both logs. No metadata stripping or diagnostic pattern filtering is introduced. Fixed ZIP entry metadata makes the envelope repeatable for identical payload bytes. Preserve the source and variant checks, host 101/702 oracles, ART counts and cleanup checks. The four-row CI rerun with real javac remains required; host compilation and local packaging checks cannot replace ART.

Local validation uses the installed Linux JDK 21 compiler module through an explicitly recorded javac adapter and unchanged ct.sym profiles from the existing JDK 21.0.13.1. It does not claim that the local environment supplied a native javac launcher. The CI producer continues to require its real JDK 21 executables.
