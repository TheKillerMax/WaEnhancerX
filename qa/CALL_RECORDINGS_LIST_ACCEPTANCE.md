# Call recordings list and playback acceptance

## Source scope

This focused change ports the storage, permission, sharing and playback work
from PR #93 onto the current recorder and microphone-fallback candidates.
It keeps the current `HookProviderIpc` calls and acknowledged preference writes.
It changes no workflows, signing, provider authorization or manifest permission.

The production screen is not compiled as a complete Compose screen here.
The harness extracts the exact permission/state, loading, lifecycle, playback
and deletion bodies from `CallsHubScreen.kt`. Explicit Compose and lifecycle
adapters invoke those callbacks without rewriting their bodies. It also compiles
the current `CallRecordingStore`, `RecordingOutputFiles` and the current
provider's `create_call_recording` body.

## Offline command

Set `JAVA_HOME` to JDK 17 or 21 and `KOTLIN_HOME` to Kotlin 2.0.20. Supply the
verified framework dependencies, instrumented SDK JARs and AndroidX Core JAR:

```sh
python qa/android_call_recordings_list_test.py --deps /absolute/verified/deps --sdk-jars /absolute/verified/sdk-jars --core-jar /absolute/core-1.18.0-classes.jar --out /absolute/new-empty-result-directory
```

The default gate requires all 99 cases: 33 test methods on APIs 24, 28 and 34.
`--allow-test-failure` is solely for measuring a known older source with
`--source-root`; it does not alter the default candidate gate or the required
case count. Inspect `junit.log` to distinguish assertion failures from setup
or compilation failures.

The Core classes JAR SHA256 is
`d1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0`.
The runner records source hashes, extracted source ranges and dependency hashes.
Use a fresh output directory for each run.

## Executable acceptance

- App-owned external recordings and both internal recording directories remain
  readable after shared-storage permission is denied.
- Provider fallback files stay listed when external storage is unavailable,
  and after the volume returns.
- Legacy shared directories are scanned only when the API-appropriate audio
  permission is granted. The configuration tab does not request or scan them.
- Returning to the screen rechecks permission; disposing removes its observer.
- Disk enumeration runs on the IO dispatcher, preserves stored call metadata,
  accepts supported extensions without case sensitivity and sorts newest first.
- The actual FileProvider path strategy accepts the declared internal fallback,
  old internal and external recording roots, while rejecting unrelated files,
  sibling names sharing a directory prefix and canonical parent-directory escapes.
- Failed data-source assignment, preparation, start or stop still releases the
  owned player. Disposal, replacement, stale completion and reentrant stop do
  not retain or stop the wrong player.
- Confirmed deletion removes the row and index only after the file is removed;
  a refused or throwing delete leaves the file and metadata visible and reports
  failure. Existing pause and resume controls retain the current player.
- Thirty repeated failed preparations per SDK release every player candidate.

## Boundaries and device acceptance

Robolectric uses real Android Context, file APIs, Bundle, ParcelFileDescriptor
and SQLite objects, plus real temporary files.
The native media player is a controlled shadow; placeholder bytes are never
decoded or played. Permission answers and volume availability are supplied by
a Context wrapper. XML inflation is represented by feeding declared roots to
the actual AndroidX Core canonical path strategy. On Windows, the fixture first
canonicalizes paths through the real filesystem, then exposes Android slash
separators only at that strategy boundary. It leaves the library algorithm
unchanged. URI-to-file resolution, Binder authorization, share
activities, Compose rendering and recomposition are not exercised.

No microphone, actual call, root injection or hosted CI run is involved.
A module/APK build and consented device acceptance remain separate gates for
the complete UI, permission prompts, sharing intents and OEM media behavior.
Evidence from an older PR or source tree does not establish these gates for
the final published commit.
