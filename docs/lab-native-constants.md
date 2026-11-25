# Separate laboratory workflow for waexdiag JNI constants

This five-file proposal integrates the reviewed nine-file neutral probe with the
existing AVD controller. It does not change that controller, the SQLite probe,
the 21-image lock or product code. The initial experiment has only two rows:

| Target | Official image path | Application page bytes |
| --- | --- | ---: |
| api35 | system-images;android-35;google_apis;x86_64 | 4096 |
| api35-16k | system-images;android-35;google_apis_ps16k;x86_64 | 16384 |

Both rows already exist in android_emulator_lab_matrix_lock.json. They use the
reviewed Google APIs image identities, revisions, checksums and existing standard
SDK acceptance. No additional image channel or licensing exception is introduced.
The x86_64 ps16k row is application-facing simulation, not proof of a native16K
kernel or physical ARM64 compatibility.

## Production and consumption

One Ubuntu job builds the candidate x86_64 ELF and one neutral test-only APK. Its
ephemeral signing key remains in the private temporary work directory and is
deleted. The job emits two independently named SHA256 outputs: the APK and
build-result.json. Only those two files enter the producer artifact; logs use a
separate artifact. Tool archives, build work directories and key material are
excluded.

Each target job downloads that exact producer artifact. Before bootstrap or ADB,
verified_bundle checks both independent output hashes, the nine frozen source
identities, existing Java identity from the reviewed Linux preflight, the build
receipt and the APK/native alignment inventory. The same checks run again when
constructing the callback. A changed receipt cannot authenticate itself merely
by containing an expected APK hash.

The standard controller owns a new AVD, boot identity, exact API/minor/ABI, page
observation and emulator cleanup. The native callback runs only after that boot
gate and accepts only the assigned serial and the two exact target descriptions.
It delegates installation, fresh nonce, installed-APK readback, JNI constant
verification and exact-package cleanup to run_native_constants_probe.

The callback returns the controller's required status PASS only after the
specific PASS_WAEXDIAG_JNI_CONSTANTS receipt and verified removal. That complete
specific receipt remains in phase.probe. The original instrumentation log,
readback identities and producer receipt are preserved; binaries are excluded
from the runtime report directory.

## Aggregation and failure handling

A final job requires both targets from the current workflow run, attempt and
commit. It verifies the recursive report manifests, bootstrap evidence, clean
controller completion, copied producer-receipt hash and source pins. It then
revalidates the actual instrumentation log and all 14 returned values / 38
strings, checks installed and cleanup APK identities, and rejects missing,
duplicate or stale evidence. Both rows must use the same producer hashes and
fresh distinct nonces. A failed build or missing row yields BLOCKED.

The workflow is restricted to the public laboratory branch, has contents:read
only, pins its actions, and preserves logs on failure. Its activation follows
publication of the probe and the already reviewed matrix/lock dependencies.
It does not publish a product release or create a PR.

## Local review evidence versus pending execution

The local integration controls use the real pinned source lock but synthetic
APK-shaped files, mocked boot and simulated ADB. They cover both producer hashes
before boot, exact targets, callback success/failure, package cleanup, raw-log
revalidation and complete two-row coverage. These controls are not Android runs.

The required next evidence is one successful Linux producer and both actual AVD
observations. Until those receipts exist, JNI loading, the full product and
physical-device compatibility remain unproved. The resulting coverage is limited
to the public waexdiag constants; returned command strings are never executed.

The Windows integration run used a local import-only fcntl boundary because that
standard module is Linux-specific. Its ioctl implementation always raises, and
zero calls were observed. No published helper or candidate source was changed
for that boundary. The workflow runs the same six tests on Linux with the real
module before downloads/build; that Linux run remains required.
