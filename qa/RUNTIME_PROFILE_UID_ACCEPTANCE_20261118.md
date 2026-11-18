# Qualify WhatsApp process evidence by Android application UID

## Observed problem and supported context

Base: upstream/fork `main@0aaffab0270a3d0832bef2895f6457f3792fd74a`.

`RootProbe.processListCommand()` used `ps -A -o PID,NAME` and `parseProcessList()` stored only the process name and PID. `WhatsAppPackageDetector.detectWhatsAppApps()` compared a target's persisted injection PID against that **global** list without distinguishing Android users. Two installed `com.whatsapp` apps in personal/work profiles have identical process names but different UIDs. A PID reused by the other profile in the same boot could therefore appear `InjectionEvidence.CURRENT` for the wrong user. This is an evidence/diagnostics correctness risk, not proof that a currently installed hook failed.

On the **actual** private API34 laboratory emulator, read-only `adb shell ps -A -o UID,PID,NAME` successfully returned numeric identities, including `1010197 11820 com.whatsapp` (user 10/work) and later `10197 12732 com.whatsapp` (user 0/personal). `cmd package list packages --user 0/10 -U` independently confirmed owner UID `10197` and work UID `1010197`; corresponding `com.waenhancer` UIDs were `10191` and `1010191`. An earlier snapshot only had the work-profile WhatsApp process; changing PIDs are expected and not treated as stable test identities. No UI, preference or account operation was performed.

## Current-source correction

- Request `UID,PID,NAME` from the same filtered, bounded root `ps` invocation; retain the older `ps` command as a **diagnostic-only** fallback.
- Extend `XposedRuntimeSnapshot` with a deeply immutable UID-indexed PID map and explicit UID-qualification flag. Preserve its existing constructor fields and name-only `pidsFor()` for non-authoritative diagnostics.
- Reject all UID-qualified answers when source rows are partial, malformed, mixed with legacy USER/PID layouts or lack numeric UID. `pidsForUid` returns **null** (not an empty set) when it cannot establish ownership; an exhaustive fully qualified list may legitimately return the empty set for a stopped process in the expected UID.
- Resolve expected UID from `PackageInfo.applicationInfo.uid` in the detector's **current Android user**, then pass only `pidsForUid(packageName,uid)` into the existing PID/boot classifier. Do not infer ownership from the shell's UID, a foreground activity, package-name equality, or the presence of another profile's process.
- No permission changes, hook modifications, licensing replacements, signing changes or real WhatsApp event sends.

The provider and LSPosed scope remain separately user-isolated; these changes narrow incorrect *injection evidence*, not runtime feature compatibility. Same-UID PID reuse within the same boot is a residual risk that requires start identity/nonce to eliminate completely; this patch does **not** claim to solve it.

## Executed control and negative mutation

**PASS:** Windows 11 laboratory, JDK 17.0.20.1, Kotlin 2.0.20, actual current `XposedRuntimeInspector.kt` + `InjectionEvidence.kt`, deterministic `SystemClock` adapter only. `qa/test_profile_pid_evidence.py` executed **34 independently specified JVM cases, 0 failures**, including two numeric users with identical process names, other-user PID reuse, stopped/changed/unavailable distinctions, invalid expected UIDs, legacy USER layouts, malformed and mixed rows, snapshot completeness, Business package, and immutable nested maps.

**PASS negative control:** a separate copy deliberately changed `pidsForUid` to return the existing unqualified `pidsFor(packageName)`. This mutant **compiled** and the unchanged oracle rejected it (nonzero exit with the wrong UID PID result). It was never included in the source branch.

Evidence directory: `C:\WAEX-Lab\evidence\waex-profile-uid-20261118\candidate-01`. Candidate JAR SHA256 `6f39c4c378294a28bf2ac8a749319a57b8e62ee81526a40d65b42bc371ed0ef5`, mutant JAR SHA256 `69e2339fcd55bc305c13c4d6a06a8cedbf7f647ccaaaaf55a6d7e3ac48826ad7`. Production source SHA256 fingerprints are in `result.json`. The same test is configured for a JDK17 GitHub Actions workflow; its CI result must be checked on the final PR SHA.

**NOT_VERIFIED:** hook execution, profile-specific provider report identity, Android versions other than API34, WhatsApp versions beyond the observed `2.26.43.76`, full WAEX APK build, UI state, private modules or remote recipients. The JVM fixture compiles the actual parser/classifier but does **not** run Android root or LSPosed.

## Relationship to older PR and integration safety

[Existing upstream PR #98](https://github.com/WaEnhancerX/WaEnhancerX/pull/98) also addresses cross-profile PID attribution but is an older, much broader 37-file proposal based on an earlier runtime model; its head `324fc9e7c4cadd084e437e5a609d1509dfe67db7` is currently nonmergeable against main. It uses per-PID `/proc/status` validation and additionally changes runtime queue/preference logic. **Do not merge the overlapping alternatives blindly.** This focused candidate targets the newer shared `RootProbe` architecture, adds new API34 observed evidence, and intentionally does not port that unrelated queue/prefs logic. A maintainer should choose or reconcile the UID-identity behavior while preserving history and testing both.

Relevant primary contracts: [AOSP Toybox `ps` fields](https://android.googlesource.com/platform/external/toybox/+/3b3281367ccb9f41ef952c7e1ad520fad4b792f0/generated/help.h), [Android 14 UserHandle UID range](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android14-gsi/core/java/android/os/UserHandle.java).

## Acceptance and recovery

1. Re-run `python3 qa/test_profile_pid_evidence.py --out <fresh>` with real Kotlin/JDK; require all 34 cases plus compiled-mutant rejection.
2. Run the dedicated GitHub Actions source contract on the exact published head, verify SHA/toolchain and zero failures.
3. On a controlled Android lab, compare numeric `ps` UIDs with `PackageInfo.applicationInfo.uid` separately for users 0 and 10, distinguish absent from unavailable, and verify the actual UI only when safe.
4. Verify no regression on older Android variants; where numeric UID is unavailable, show process observation unavailable rather than a false confirmation. Do not claim universal compatibility from this single API34 emulator.

Recovery is a normal revert of the isolated UID-evidence patch; it changes no persisted schema, key, Android user, target data or actual injection hooks.
