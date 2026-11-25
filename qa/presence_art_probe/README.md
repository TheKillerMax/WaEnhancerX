# ART counterpart for the presence pixel contracts

This is a separate public QA APK for Android emulators. It exercises the same
two pixel oracles that fail on Robolectric 4.17 API 24/25, together with two
independent Android Canvas/View controls. It does not contain the WAEX app,
Xposed hooks, WhatsApp, licensing sources, network access or user data.

## Source and expectations

The builder imports the existing `qa/android_presence_row_test.py` and calls its
unchanged `harness` extractor. The ten renderer method bodies, fields and
companion are preserved. The resulting positive `RendererHarness.kt` must match
the separately supplied, already executed Robolectric harness when
`--reference-harness` is used. It compiles these complete production files:

- `PresenceStateStore.java`
- `HostResourceIds.java`
- `UiText.java`
- `DisplayLocalePolicy.java`

The row/measurement/coordinate helpers and the two pixel assertions come from
`qa/fixtures/PresenceRowRenderingTest.kt`. The builder rejects unexpected staging,
coordinate or bitmap declarations and verifies that all four original assertion
strings remain identical. It adapts calls around the two `pump()` boundaries:
view work runs through `Instrumentation.runOnMainSync`, waits run on the
instrumentation thread, and rows attach to a real Activity window. Android's
configuration context supplies mdpi geometry for the unchanged 400×80 bitmap.
No `Resources`, `View`, `Canvas`, `Handler` or store result is replaced by a stub.

The two compile-only declarations, AndroidX `NonNull` and module `R.string`
numeric bindings, are extracted from the existing public runner. UiText's real
English fallback remains in scope; resource localization and hook discovery are
separate tests.

The APK uses min SDK 24 and target SDK 28, preserving the target SDK explicitly
set by the original fixture. This target is an experimental fixture parameter,
not a change to the project's compileSdk/targetSdk or a compatibility claim.

## Four cases on each requested API

| Case | Oracle |
|---|---|
| `pureCircleRasterizesWithoutWaex` | A plain circle's center equals RGB(37,211,102). |
| `plainAndroidViewDrawsAndClearsWhenHidden` | A plain Android View draws green and clears after GONE. |
| `nativeCanvasContainsGreenDotAndClearsOffline` | The production renderer draws green; the same coordinate clears after a real offline store update. |
| `invalidationClearsTheNativeGreenPixel` | The production renderer draws green; the same coordinate clears after real store invalidation. |

The historical API 24, 25 and 26 profiles remain admitted. The current workflow
executes only the additional API 28/34 profiles with 4 KiB pages and API 35 with
simulated 16 KiB pages on x86_64, four cases and seven PNGs each. Each row records
actual API, package, density, pixel values, failures/errors and zero skips. These cases do not
replace or change the four preserved Robolectric FAIL results.

## Offline build

Required existing inputs: JDK 21, Kotlin 2.0.20, Android SDK platform 36 and build
tools 36.0.0, JUnit 4.13.2, Hamcrest core 1.3. The builder downloads nothing,
does not run project Gradle, creates a QA-only signing key and deletes that key
after signing (including a failed signing attempt). It never installs.

The Kotlin home must have exactly the nine regular JARs specified by
`qa/class_metadata_art_probe/toolchain-lock.json`, including the compiler's
reflect 1.6.10 dependency. The laboratory builder prepares this closed home from
the pinned Maven Central bytes. A full Kotlin distribution with extra plugins
does not satisfy this contract. The Presence lock also pins the unchanged
ClassValue helper and its lock before importing them. Java and native javac must
both report version 21 from the selected JDK. Inherited Java/Kotlin options are
cleared; the offline JVM commands retain an explicit two-processor limit.

```sh
python build_presence_art_probe.py \
  --source-root /path/to/reviewed/waex-source \
  --out /new/evidence/presence-positive \
  --sdk /path/to/android-sdk \
  --java-home /path/to/jdk21 \
  --kotlin-home /path/to/closed-kotlin-2.0.20 \
  --deps /path/to/existing/junit-and-hamcrest \
  --reference-harness /path/to/executed/RendererHarness.kt
```

`source-manifest.json` pins production inputs and oracle strings. The successful
`build-result.json` adds tool/JAR/APK hashes and marks `art_execution: NOT_RUN`.
Compilation and signing success do not certify a device result.
Every command has separate raw stdout/stderr logs and hashes. D8 succeeds only
when both streams are empty, without removing or filtering diagnostics. Compiler
and tool inputs are checked again before a successful build result is written.

`--variant wrong-dot-color` and `--variant keep-dot-visible` create separate
causal negative candidates. They retain the same oracles. They have not been
executed on ART; their failures must be kept as negative-control evidence rather
than substituted for a positive matrix result.

## Explicit emulator execution

The matrix controller must own the disposable AVD and record the system-image
identity, ABI and page size. Those are controller preconditions: the launcher
checks the explicit serial, QEMU, API and package absence, but does not establish
AVD ownership or certify the ABI by itself. It requires an explicit page-size
expectation; Instrumentation measures `Os.sysconf(OsConstants._SC_PAGE_SIZE)`
inside its own process. Both the recovered JSON and the matching final Bundle
must agree with that expectation. The wrapper also requires the shared boot
controller to observe the same application-facing page size. The x86_64 ps16k
profile remains a simulation, not a physical ARM64 or kernel-page-size result.

The launcher only accepts an explicit `emulator-NNNN` serial and verifies QEMU,
the requested API and the frozen APK hash before installation. The QA package
must be initially absent. It uses `install -t` for the `testOnly` package and
pulls the installed APK to verify its SHA-256. It never selects a device
automatically, reboots, wipes or operates a physical phone. It requires a fresh
output directory and uses a unique nonce for on-device evidence, so an earlier
result cannot be mistaken for a current run.

```sh
python run_presence_art_probe.py \
  --adb /path/to/android-sdk/platform-tools/adb \
  --serial emulator-5554 --api 24 --page-bytes 4096 \
  --apk /path/to/presence-art-positive.apk \
  --expected-sha256 SHA256_FROM_BUILD_RECEIPT \
  --out /new/evidence/api24-presence
```

The launcher accepts a positive matrix row only with exactly the four named
cases, four PASS, zero failures/errors/skips, matching API/run nonce and PNG
evidence. A successful final Instrumentation code (-1) must appear exactly once,
with no FAILED/ABORTED marker, and its qa_result Bundle must match the recovered
JSON. It retains failed instrumentation output. After copying reports, it
uninstalls only the exact QA package installed by this invocation and checks
that the package is absent. A pre-existing package is never replaced or removed.
If installation is ambiguous, cleanup requires the installed APK to match the
candidate bytes. A matrix PASS also requires successful cleanup; host reports,
PNGs and the pulled APK remain available.

Android lifecycle references:

- https://developer.android.com/reference/android/app/Instrumentation#runOnMainSync(java.lang.Runnable)
- https://developer.android.com/reference/android/app/Instrumentation#waitForIdleSync()
- https://developer.android.com/reference/android/app/Instrumentation#startActivitySync(android.content.Intent)

Page-size API reference: https://source.android.com/docs/core/architecture/16kb-page-size/getting-page-size
