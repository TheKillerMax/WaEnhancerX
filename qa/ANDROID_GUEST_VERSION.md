# Android guest version properties

Run `45560826392`, attempt1, commit
`6b6ac021f05565b2a6e91e65b51f39870a4d1869` built the ClassValue probes with the
closed Kotlin2.0.20 toolchain. API30, API33 and API34 completed their ART gates.
API24 stopped before ART execution: the optional command
`getprop ro.build.version.sdk_full` returned255 with one newline of output.
The emulator was still alive and was reaped; accepted license files were
unchanged. This observation does not identify the internal reason for exit255.

The major/minor API contract was introduced at API36. The controller now omits
that unsupported extension on API24–35 and records a separate policy receipt.
It still requires the actual major API, ABI, package manager and application
page size on those targets. A nonzero minor version in their image metadata
remains an error. API36+ still requires a successful property command and an
exact major/minor match; errors, empty values and mismatches remain blocking.

The previous21-target success remains evidence for its original source and
run. It is not relabelled as validation of this change. A new ClassValue run
and any triggered matrix run must retain their own producer, attempt and
complete artifact inventory.

References inspected2026-11-25:

- https://developer.android.com/reference/android/os/Build.VERSION#SDK_INT_FULL
- https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-16.0.0_r4/core/java/android/os/Build.java

`test_android_guest_version.py` uses synthetic command responses to check the
lookup/version contract. Those host controls are separate from Android ART
execution. The change does not suppress shell failures in other commands,
retry a failed test, or treat an unsupported property as a measured value.
