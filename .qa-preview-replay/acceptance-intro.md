# Media preview ownership, bounded UI publication and current lifecycle

## Source and integration

PR #90 is reconciled with upstream 4750124e36223dd21d8535c14f2fb658025d8480. Retain upstream's waex cache/resource names, shared ViewHookDispatcher, fallback only when both primary containers are missing, and detach cleanup for the global-layout listener. Do not replace those current paths with the historical preview file.

Each preview owns its task, HTTP call, dialog, video and created temporary file. Only a file created by that preview is eligible for cleanup. Cache location, filename or a mediapreview_ prefix never transfer ownership of host media. The one-worker executor retains at most one pending preview; closing a session cancels its registered work/call and removes its queued task.

## Additional fixes in this reconciliation

Register UI callbacks under the same session monitor used by cancellation. A cancelled session cannot pass the current-session check and register a callback after cancellation has finished removing its messages. The callback itself still rechecks identity.

Keep one pending progress runnable per session. New observations update its latest percentage/size rather than enqueueing one message per read. Clamp displayed percentage to 0..100; an underestimated content size must not flood a paused UI queue. This does not establish a global bound on all Android messages.

Retain an explicit ownership slot only for newly decoded, not-yet-published bitmaps. Cancellation recycles a pending owned bitmap; a result arriving after cancellation is recycled immediately. Published images and host-owned bitmaps are not recycled by this pending-result path. Native full-size decoding is unchanged and not guaranteed interruptible.

## Reproducible QA

    python3 qa/android_media_preview_test.py --out /tmp/waex-preview
    python3 qa/mutate_media_preview_lifecycle.py --out /tmp/waex-preview-mutants --deps /tmp/waex-preview/deps --dexkit-jar /tmp/waex-preview/public-apis/dexkit-2.2.0.jar --http-api-jar /tmp/waex-preview/public-apis/okhttp-4.12.0.jar

JDK 17+, a complete Kotlin distribution via KOTLIN_HOME, Python and Maven are required. Optional dependency/API/SDK paths reuse verified public artifacts. New output directories are required; failed runs are retained. Compilation launches the real Kotlin compiler JVM, avoiding Windows launcher/classpath splitting.

The complete MediaPreviewHook, BaseFeature, HookRegistrar, ViewHookDispatcher and HKDFv3 compile. One compilation uses the real OkHttp 4.12 and DexKit 2.2 APIs. Execution uses Robolectric 4.17 Android dialogs/views/handlers on API 24, 28 and 34. HTTP, host database discovery, Xposed transport and audio decoding remain explicit boundaries. The runner checks every generated R.string name against real default XML resources before compilation; that is not a full Android resource/package build.

Initial common matrix: 12 methods x 3 SDKs = 36 JUnit executions. Unchanged current main compiles and completes with 33 assertion failures. The initially reconciled candidate passes 36/36. The expanded final suite has 19 methods x 3 SDKs = 57 executions, all passing. Do not attribute its seven new tests to the earlier 36-case baseline or add repetitions into unique coverage.

The expanded suite checks a 5,000-event progress burst, cancelled pending UI, bitmap ownership before and after cancellation, original bytes of host-owned cache files, response-body closure after late cancellation, and a two-thread lock-order probe. Four deliberately compiled regressions complete all 57 and are rejected by 3, 3, 3 and 6 assertion failures: unbounded progress, leaked pending bitmap, unlocked UI registration and uncancelled HTTP call. Setup/compilation failures never qualify as mutation detections.

## Manual acceptance

With a legitimate contributor APK, compare rapid image/video opens, back/dismiss/window teardown and Activity recreation. Exercise delayed and cancelled HTTP, local files, media formats, screen-scoped install/dispose, and the current message lookup. Hash host files before/after; inspect actual owned temporary cleanup and native player behavior. Test supported WhatsApp versions and Debug/Release independently. Record module/host SHA, Android/profile/framework and sanitized diagnostics.

## Explicit remaining limits

No candidate APK was installed. No real messages or calls were made in this reconciliation. The tests do not establish native DexKit matching, actual host selector support, codecs, remote HTTP behavior, file identity from a WhatsApp database, ARM64/16 KiB compatibility, or cross-profile IPC.

Encrypted downloads still use the inherited whole-buffer decryption path, and image decoding still uses the inherited full-size decoder. No bounded memory, authenticated-media result, improved cryptographic integrity, total-operation deadline or immediate abort of native/DB work is claimed. Those require separate narrowly scoped changes and proper format/host evidence. The fixture currently exercises local media and unencrypted synthetic newsletter downloads; it does not certify encrypted downloads.

The observed performance benefit is bounded pending work and coalesced UI updates within controlled tests, not a measured end-user startup, battery, throughput or frame-time improvement. Preserve existing general CI; a focused preview PASS is not whole-project acceptance.
