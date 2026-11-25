# Pinned synthetic Opus JNI experiment

## Acceptance and scope

This experiment tests the original x86_64 library from
`io.element.android:opusencoder:1.2.0` in fresh, controller-owned Android 35
AVDs with 4096-byte and simulated 16384-byte application pages. Android performs
encoding through the published Java/Kotlin wrapper. A separate pinned
libopus 1.5.2 build on the Linux host decodes the returned Ogg stream.

A passing row requires all of the following:

- The unique producer APK, current commit/run/attempt and both producer
  receipts match their independently supplied job-output hashes.
- The reviewed image, ABI, major/minor version, application page size, owned
  emulator identity and unprivileged shell match the lab contract.
- No probe package exists before installation. A fresh installed-APK readback
  matches the producer before execution and again before removal.
- Both serial PCM cases complete all 157 successful JNI calls and 189 Android
  checks. There is exactly one successful release after each successful init.
- The nonce-bound chunk transport is complete, ordered and hash-consistent.
  Instrumentation finishes successfully without duplicate or error fields.
- The host checks Ogg page checksums, lacing, sequence, BOS/EOS, Opus headers,
  granules, pre-skip and final trim, and decodes the exact expected sample count.
- Decoded energy, clipping, DC offset and frequency match the predeclared
  synthetic tone criteria. Android owns and removes its temporary directory;
  the controller verifies package removal, reaps its emulator and confirms
  that accepted SDK-license files did not change.

Failures retain the raw transcript, producer identity and independent execution
and cleanup errors. A mismatching installed APK is never uninstalled. The
surrounding boot controller still terminates only its owned disposable AVD.

## Fixed inputs

| Input | SHA-256 |
|---|---|
| Official 1.2.0 AAR | `e93855fc25d075d66361a03ea1d353bbb029054e6683b7bbc4c82eedad7a91e5` |
| Original x86_64 `libopuscodec.so` | `4f2b782362aeda7da6f9f4a0bdfdb30a310a824a91da1f2e770b4f65780864dc` |
| Original wrapper `classes.jar` | `1f90e41d2a9dc388510568f2cea3605a435a3e735bdd76bb348dd6baafba2578` |
| Xiph libopus 1.5.2 release source | `65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1` |
| 48 kHz PCM asset | `00cde5d613eaadc51c6b3e8b66f827a57f681aebbd1c9228bc365d082a6d92ba` |
| 16 kHz PCM asset | `4e57713a4022f94e833ea3f8567f1eec0204f9db2b32ae63f6bbcb1ab9ce59e5` |

The published runtime closure is Kotlin stdlib 2.1.21, AndroidX
annotation-jvm 1.9.1 and JetBrains annotations 13.0. Exact URLs, lengths and
digests are in `android_opus_probe/dependency-lock.json`. Base class bytes,
including Kotlin metadata, remain unchanged. The original downloaded archives
are retained; multi-release/module metadata and unrelated archive resources
are excluded from the D8 input projection and inventoried in the build receipt.
No lower Kotlin version is substituted for the encoder's declared dependency.

The APK uses minSdk 24, targetSdk 36, no permissions and no activities. It is
test-only, non-debuggable and disallows backup. Its only native library is
stored uncompressed with `extractNativeLibs=false`. The builder checks ELF
LOAD alignment and native ZIP data alignment with a 16 KiB requirement, then
verifies the signature and alignment of the final APK. Static alignment alone
does not establish successful dynamic loading.

The JDK 21/SDK 36 tools are existing runner inputs, individually hashed before
and after the build. D8 must emit no stdout or stderr diagnostics. Signing uses
an ephemeral QA key that is removed before successful publication. Each run
produces one APK reused by both targets; its bytes are not expected to be
identical across independent runs with different ephemeral signing keys.

## PCM and output oracle

| Case | Input | Frames and bitrate | Required host decode |
|---|---|---|---|
| `pcm48k` | Mono S16LE, 48 kHz, 96000 samples; 440 Hz then 880 Hz | 100 frames of 960 samples; 32 kbps then 64 kbps at sample 48000 | Mono 48 kHz, 96000 samples after pre-skip/trim |
| `pcm16k` | Mono S16LE, 16 kHz, 16000 samples; 660 Hz | 50 frames of 320 samples; 32 kbps | Mono 48 kHz,48000 samples after pre-skip/trim |

Input amplitude is 12000. Assets use a deterministic Decimal sine calculation
and half-even integer rounding, with whole-file hash checks on Android.
Frequency measurements use the central 0.8 s of each 1 s tone segment. Normalized
RMS must be 0.15–0.40, absolute DC at most 0.02, clipped fraction at most 0.01,
and energy at the expected frequency at least 0.75. These bounds are fixed
before Android execution; output equality is not required from a lossy codec.

The host decoder is built from the checksum-pinned official Xiph release,
with a recorded configure recipe, compiler/tool identities and unchanged
source-file hashes. It is not installed system-wide. The runtime jobs check
its exact library and receipt hashes before loading it, and recheck the
library after validation. Its complete COPYING file travels with the artifact.

## Host controls and real Android evidence

`test_android_opus_probe.py` creates a real host-encoded corpus to exercise
the parser, decoder and deliberately malformed transport/stream cases. These
logs are simulated instrumentation and are labelled as host-only evidence.
`test_android_opus_controller.py` uses synthetic ADB responses to verify
producer identity and cleanup decisions, including existing packages, failed
installation, failed validation and a changed APK before removal. Both suites
run normally and with Python optimization enabled.

Only the `opus` workflow jobs execute JNI on Android. The output consists of
the unique APK artifact, the decoder artifact, producer evidence and one
runtime artifact per target. Review the entire current-run inventory and
recompute each report/manifest and payload hash before claiming both targets.

The initial pilot does not qualify WAEX, WhatsApp, LSPosed, recording,
playback, concurrent encoders, long-running native lifecycle, physical ARM64
hardware or every Android version. The observed encoder JNI uses a global
codec instance; this experiment deliberately runs two bounded serial cases.
The inspected binary/source do not justify a production dependency upgrade.
The public source repository exposed no 1.2.0 tag during inspection, so the
experiment pins the released binary without claiming a source rebuild match.

## Primary references

- https://repo.maven.apache.org/maven2/io/element/android/opusencoder/1.2.0/
- https://www.rfc-editor.org/rfc/rfc3533
- https://www.rfc-editor.org/rfc/rfc7845
- https://opus-codec.org/docs/libopusenc_api-0.2/group__encoding.html
- https://opus-codec.org/release/stable/2024/04/12/libopus-1_5_2.html

Third-party license texts and the source/binary provenance limitation are
preserved in `android_opus_probe/licenses/` and packaged in the test APK.
