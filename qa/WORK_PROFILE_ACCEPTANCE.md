# Manager operations in Android work profiles

## Confirmed failure and correction

The manager previously used an unqualified "am force-stop" followed by Monkey.
AOSP's ActivityManager shell initializes an unqualified force-stop to USER_ALL.
Monkey discovers launcher activities for the foreground user. A work profile
has a separate Android user ID even while its parent remains in the foreground.
The old stop and launch operations therefore did not name the same installation.
The root updater also hardcoded "--user 0" independently of the manager's profile.

AndroidUserScope derives the user ID from the manager Context's application UID,
using AOSP's documented "uid = 100000 * userId + appId" relationship. The process
UID must belong to the same user. Negative UIDs and Android's special all/current
user selectors are rejected.

Before stopping a supported package, AppRestartHelper resolves its launcher with
that same Context's PackageManager and checks the component package, installed
package name and application UID. Both privileged restart commands name that
user explicitly. The launch names the validated component through "am start -W";
only a complete "Status: ok" line on a successful command counts as an acknowledged
launch. Missing packages, foreign components/UIDs and invalid component names
fail before force-stop. Root denial and launch failure keep the existing local
Context fallback; an already stopped app does not receive a subsequent self-kill
broadcast. The bulk restart follows the same target validation. Its existing
behavior after a failed root launch is unchanged: it does not check that launch
result or use the individual restart's fallback before relaunching the manager.
The new bulk cases verify target selection and component rejection; they do not
exercise a rejected root launch after a successful bulk force-stop.

The root updater chooses that same explicit user instead of user 0. This selects
the installation user; it does not create independent APK versions across users
or override Android's package-update semantics. Package code updates may also
affect users where the same package is already installed. Existing APK identity,
version, copy-size and temporary-file checks remain active.

This change concerns the destination of manager operations. It does not prove
that the entire reported 1.7-to-2.0 work-profile injection regression is fixed.

## Framework regression runner

    python3 qa/android_work_profile_test.py \
      --out /tmp/waex-work-profile-framework \
      --maven-repo /tmp/waex-work-profile-m2

Use a new output directory and provide JDK 17 or later, javac, Kotlin and Maven.
The runner pins Robolectric 4.17, JUnit 4.13.2 and Android compilation classes
from android-all:14-robolectric-10818077. It uses the project's pinned OkHttp and
Kotlin versions. Dependency resolution uses the shared bounded Maven helper.
CI runs this as a non-optional job and uploads JSON identities/results and compiler,
dependency and JUnit logs even if the test command fails.

For an existing dependency cache and flat offline SDK directory:

    python3 qa/android_work_profile_test.py \
      --out /tmp/waex-work-profile-offline \
      --deps /path/to/robolectric-and-android-jars \
      --extra-deps /path/to/okhttp-and-okio-jars \
      --sdk-jars /path/to/android-all-instrumented

The complete production AppRestartHelper, RestartTargetPolicy, UpdateDownloader,
UpdateTransferPolicy and candidate AndroidUserScope files are compiled unchanged.
The runner copies only the exact one-line normalizeVersion function from
ReleaseRepository, recording that source file's identity separately. It does
not claim to compile the complete release repository.

Twenty-five scenarios run on API 24, 28 and 34: exactly 75 executions. They cover
owner user 0, work-profile user 10, secondary user 11, a supported clone, a launcher
class from another Java namespace, unavailable packages, invalid target names and
components, negative/foreign Context UIDs, foreign target UIDs, root denial,
rejected/timed-out/malformed launch results, duplicate requests, bulk restart,
three updater users, invalid APK/version, foreign updater Context and failed copy.

Android Context, Activity, Intent, PackageManager, Handler and Toast run under
Robolectric. Profile UIDs and package/archive metadata are controlled fixtures.
Two invalid-component scenarios override only getLaunchIntentForPackage; other
framework calls delegate directly. Negative installer assertions join the actual
production worker thread before inspecting its commands. RootCommandRunner is
an explicit endpoint fixture that records arguments and never invokes its
subprocess starter. The test's ZIP is not a generated or signed Android APK.
The fixture's install response is a deliberate failure so no self-termination
path runs. Bulk manager termination is also excluded from the main-looper drain.
Display localization, scope lookup and the normal external installer are adapters.
Real OkHttp classes are used, but no HTTP request is made.

The final candidate passes 75/75. The same test fixture against the complete
a565e1a1a50ebfe5d633e8cd0d43c6dc6025a8ac sources executes 75 cases and produces
39 assertion failures. The accepted negative baseline uses
"--expect-assertion-failures 39"; the default always requires 75 successful cases.
Compilation errors, unexpected exceptions, zero tests and different failure
counts cannot satisfy that control.

Six isolated negative controls reintroduced one regression each: hardcoded stop
user 0 (12 failures), hardcoded launch user 0 (12), hardcoded installer user 0 (6),
removed target-UID check (3), removed Context/process profile check (3) and loose
launch acknowledgement (3). These are repeated executions of the same scenarios,
not additional feature-coverage claims. Source, fixture and dependency hashes
are retained with the audit results.

## Device acceptance still required

Use an authorized test device with an enabled, unlocked work profile. Record
Android/OEM version, profile ID, host APK identity, WAEX APK identity and LSPosed/
Vector version. Confirm that the module and its provider are available and enabled
for the relevant profile and that the selected WhatsApp package is in that
profile's module scope. Do not assume that enabling the personal instance proves
injection or provider availability for the work instance.

1. With the same WhatsApp package installed in personal and work profiles, record
   both processes with their UIDs. Restart from the work manager and verify only
   the work instance is stopped and relaunched. Repeat from the personal manager.
   A process name or an unscoped pidof result alone does not identify a profile.
2. Repeat the bulk restart with supported WhatsApp and Business/clone packages
   installed in different combinations. Only valid targets present in the
   initiating manager's profile may be stopped. Verify the manager relaunch too.
3. Deny root, disable or remove the launcher in a disposable test installation,
   and make the work profile unavailable. Verify a failed target lookup does not
   redirect to another profile and that a later valid retry works.
4. For a normal authorized update, verify the package install operation selects
   the manager's user and the package installer still enforces its signature and
   policy checks. Observe both profiles for Android's shared package-code update
   behavior. Do not interpret "--user" as version isolation.
5. Separately verify provider IPC, preference persistence, runtime-health reports,
   hook installation and actual feature behavior in each profile. Include both
   release and debug artifacts; successful process launch is not hook verification.

No work profile was created, no real APK was installed, no su/am/pm command was
executed and no LSPosed or physical-device test was performed by this runner.
No startup-time, FPS, memory or universal feature-performance gain is claimed.

## Primary platform contracts

- [AOSP managed profiles: UID construction, separate data and profile boundaries](https://source.android.com/docs/devices/admin/managed-profiles)
- [AOSP ActivityManager shell: force-stop user default and explicit activity start](https://github.com/aosp-mirror/platform_frameworks_base/blob/android16-release/services/core/java/com/android/server/am/ActivityManagerShellCommand.java)
- [AOSP Monkey: launcher discovery uses the foreground user](https://github.com/aosp-mirror/platform_development/blob/master/cmds/monkey/src/com/android/commands/monkey/Monkey.java)
- [AOSP multi-user behavior](https://source.android.com/docs/devices/admin/multi-user)
- [AOSP multi-user testing: user-scoped installation and process storage paths](https://source.android.com/docs/devices/admin/multi-user-testing)
