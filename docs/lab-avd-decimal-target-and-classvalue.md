# Laboratory: decimal Android SDK images and ClassValue linkage

## Evidence and next controlled experiment

The prior matrix (45549534897, 214e4646a28c769997176def1dfb089e8258bc97) recorded repeated SurfaceFlinger RegionSampling SIGABRTs on the API 36.1 guest, including GoldfishMapper::readFromHost and Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma. The readiness horizon was not achieved and no SQLite probe installation was attempted on that guest. This is not evidence of an application failure.

A public report of the matching symptom describes incorrect decimal target serialization by older avdmanager versions: https://github.com/actions/runner-images/issues/14484 . The previous controller did not retain the AVD index, so the particular target=android-0 cause remains a hypothesis for our runner.

On fresh owned decimal-package AVDs, retain the original index and configuration. Verify the exact pinned image directory and owned AVD path. Accept the expected decimal target as-is; repair only the literal android-0 mismatch, and fail closed otherwise. Retain the before/after bytes and independent hashes. Do not change the image, GPU, memory, KVM, licensing, readiness horizon, SQLite probe, or its original 280 checks. Verify the metadata receipt during matrix aggregation. Integer package targets are unchanged.

The new ClassValue workflow compiles the full two class definitions at exact baseline/candidate commits and runs the original receipt fixture before producing separate DEX jars. It records the expected baseline linkage failure below API 34, and requires candidate initialization and cache checks, using fresh isolated AVDs on API 24/30/33/34. It is not an application installation or an Xposed, WhatsApp, real ARM64, DSU, or physical-device test. A successful host build or simulated oracle test must not be counted as ART execution.

## Validation

Local host controls retain the original checks, add byte-preservation and rejection cases, and use an import-only fcntl sentinel on Windows. The Linux runtime matrix and the ClassValue runtime workflow remain the independent acceptance tests. Review results by their exact commit and attempt; never merge rows from different commits.
