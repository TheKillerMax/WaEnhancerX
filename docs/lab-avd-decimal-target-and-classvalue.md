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
