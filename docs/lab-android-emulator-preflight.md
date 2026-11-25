# Android emulator lab: metadata and KVM preflight

This is an isolated experiment for the public fork `TheKillerMax/WaEnhancerX`, on
`lab/android-emulator-matrix-nightly8-20261124`. It adds no application behavior.
Its workflow is separate from the normal source QA and nightly release workflows.
A future PR touching these protected paths requires the separate R5 review.

## First run

Publish the lab files together on the lab branch. The branch-specific push
starts one `ubuntu-24.04` job with a ten-minute limit and `contents: read`.
The workflow also declares `workflow_dispatch`, but the first run uses push:
GitHub documents a default-branch condition for the manual trigger and its UI.
No default branch change is needed for this experiment.

The job verifies the named repository, exact branch and public visibility again
inside Python. It uses preinstalled Python, Java and Android SDK management tools.
Each disposable runner first grants only its own non-root UID read/write access
to `/dev/kvm`, preserving existing ACL entries and the effective-rights mask.
There is no group membership, udev rule, global chmod or persistent host change.
The bootstrap verifies the stable Google catalog against emulator 37.3.10,
build 16970787, Linux x64 archive size 350068887 and SHA-1
`5f7314368fc6c05c937f6991bb4106214dc389e7`. Only after the SDK's normalized
license hash is already accepted does the official SDK installer install that
package, with stdin closed. It never accepts a license or replaces an existing
emulator. Version, build and package metadata must match the pin afterwards.
The official SHA-256 reference is
`a4405349d8a9c52136ab7861e5331dc40e85574bd91cb8889a298a2ff4c52e26`;
archive download/checksum validation is delegated to the SDK installer, so this
reference is not described as an independently measured download hash.
The same bootstrap must run in every future pilot job because runner setup is
ephemeral. Its receipt is uploaded separately from the read-only inspection.
The checkout and artifact actions retain the immutable pins already used by the
repository: `11bd71901bbe5b1630ceea73d27597364c9af683` and
`4cec3d8aa04e39d1a68397de0c4cd6fb9dce8ec1`, respectively.

## What the preflight measures

- Linux CPU, virtualization flags, memory, available disk and runner image version.
- `/dev/kvm` access, KVM API version 12 and vCPU mmap size. These are query ioctls;
  no VM is created. The bootstrap's runner-specific ACL change is recorded
  separately before these read-only queries.
- SDK, emulator, ADB and Java versions, executable/launcher SHA-256 identities,
  QEMU identity when present, and `emulator -accel-check`.
- Existing NDK, CMake, build-tools and command-line-tools revisions from their
  `source.properties`, including whether NDK `27.0.12077973` and CMake `3.22.1`
  needed for a separate native build are already installed. Neither is installed
  by this preflight or by its emulator bootstrap.
- The stable SDK package list and three fixed Google XML metadata endpoints.
  Metadata responses are bounded at 4 MiB and redirects are rejected. Download
  URLs, sizes, checksums and minimum emulator revisions are recorded, not fetched.
- Stable x86_64 candidates for each API from 24 through 37, plus the explicit
  API 35 16 KiB image. Selection first requires presence in the SDK list and
  an already-accepted license; Google APIs is preferred among eligible images.
  The current accepted-license selection uses AOSP for APIs 27, 31 and 32 and
  `system-images;android-37.0;google_apis;x86_64` for API 37. Selection is confirmed
  independently against the runner's SDK package listing. AOSP selections test
  Android OS/SQLite behavior and do not establish Google Mobile Services coverage.
- Existing license-file hashes and SDK-normalized license-text SHA-1 matches using the
  Android SDK algorithm. No license acceptance file is created or changed; no
  interactive license command is run. Missing acceptance produces `BLOCKED`.
- SDK package metadata and license identities before and after inspection.
  The bootstrap separately permits only the emulator package's metadata to change;
  existing license files and every other package's metadata must remain unchanged.

The current API 37.0 catalog entry requires emulator 37.2.11 or newer. The exact
37.3.10 bootstrap pin satisfies that declared requirement; successful preflight
still does not establish that this or any other Android image has booted.

`preflight-result.json` is `PASS` only if the host/tool/listing checks and all
15 catalog/license entries are confirmed. Any missing requirement yields exit 2
and `BLOCKED`, while reports are still uploaded. `catalog.json` contains targets
and archive metadata; `installed-component-properties.json` contains the SDK
component revisions. A manifest hashes the generated report files.

Only bounded diagnostic reports are uploaded, with one-day retention. There is
no SDK/image cache, APK, user account, secret, WhatsApp data or memory dump.
GitHub documents standard hosted runners as free for public repositories; larger
runners are separately billable and are not selected here. The actual runner's
free disk is measured; the documented 14 GB disk allocation is not assumed to
fit all images together.

## Proposed second phase, after reviewing the real preflight

1. Confirm actual KVM usability, disk space, accepted licenses and tool revisions.
   Resolve any missing minimum emulator version in a separate reviewed change.
   Do not silently accept a new license or change the Windows host.
2. Pin one package path, revision and official archive checksum per matrix entry.
   Keep the preflight catalog as evidence; recheck metadata before installation.
   Use one image and a fresh AVD per disposable Linux job, with bounded downloads
   and a disk requirement derived from that image. Do not install all images in
   one runner or upload the SDK, system image or AVD userdata as an artifact.
3. Start with one API 24 job and one API 35 16 KiB job. Require hardware
   acceleration, bounded boot time, a dedicated ADB serial, completed Android
   boot, the exact SDK level, x86_64 ABI and page size exposed to applications. For 16 KiB,
   `adb shell getconf PAGE_SIZE` must return `16384`; a package name alone is
   insufficient. Standard-image page size must also be recorded and checked.
   The x86_64 16 KiB target simulates application-facing 16 KiB behavior while
   its kernel remains in 4 KiB mode; this does not validate real ARM64 16 KiB hardware.
4. If these probes succeed, expand to all 14 API levels plus the 16 KiB target,
   with a small concurrency limit, an explicit result for every entry and no
   success inferred from skipped or unexecuted matrix entries.
5. Build the reviewed neutral SQLite probe once with an ephemeral job key; pin
   that APK's SHA-256 and use identical bytes throughout the matrix. Verify its
   package, min SDK and receipt contract before installation. Keep the page size
   exposed to applications separate from SQLite's `PRAGMA page_size`. The probe does not establish
   WAEX, WhatsApp, Binder/provider or LSPosed compatibility.
6. A WAEX smoke test, if later needed, uses only a separately verified official
   release APK in an empty AVD. Native alignment, installation, launch, module
   loading and actual functional behavior remain distinct evidence. Nothing in
   this preflight recompiles, installs or validates a private application build.

## Primary references

- [GitHub hosted runners, hardware and public-runner availability](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub announcement of Linux KVM acceleration](https://github.blog/changelog/2024-04-02-github-actions-hardware-accelerated-android-virtualization-now-available/)
- [Workflow events and manual-trigger conditions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
- [Android emulator acceleration](https://developer.android.com/studio/run/emulator-acceleration)
- [Android SDK package listing options](https://developer.android.com/tools/sdkmanager)
- [Android 16 KiB page-size testing and native build guidance](https://developer.android.com/guide/practices/page-sizes)
- [Application-facing 16 KiB simulation on x86_64 and its 4 KiB kernel](https://android-developers.googleblog.com/2024/08/adding-16-kb-page-size-to-android.html)
- [Linux KVM API, query ioctls and VM creation](https://docs.kernel.org/virt/kvm/api.html)
- [Android SDK exact license-hash and acceptance algorithm](https://android.googlesource.com/platform/tools/base/+/studio-master-dev/repository/src/main/java/com/android/repository/api/License.java)
- [SDK JAXB license normalization](https://android.googlesource.com/platform/tools/base/+/studio-2023.1.1/repository/src/main/java/com/android/repository/impl/meta/TrimStringAdapter.java)
- [Official repository index](https://dl.google.com/android/repository/addons_list-5.xml)
- [Official emulator metadata](https://dl.google.com/android/repository/repository2-3.xml)
- [Official emulator archive and SHA-256 references](https://developer.android.com/studio/emulator_archive)
- [ACL modification and mask preservation](https://man7.org/linux/man-pages/man1/setfacl.1.html)
- [Official AOSP image metadata](https://dl.google.com/android/repository/sys-img/android/sys-img2-3.xml)
- [Official Google APIs image metadata](https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml)

The SDK documentation now describes the newer Android CLI as the successor to
sdkmanager. This preflight deliberately identifies and inspects the SDK tools
already on the runner; it does not install or migrate the toolchain.
