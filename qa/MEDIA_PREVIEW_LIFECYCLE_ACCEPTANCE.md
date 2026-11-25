# Media preview lifecycle acceptance

The recovered regression source comes from legacy commit 110f70413d91009a13d4354c008047a3da2b9e3f (PR90). It contains 20 test methods on Android SDK 24, 28 and 34: the complete contract is **60 cases**, not the stale 36-case value in the later runner.

All 20 methods are retained. Import-only normalization, explicit contact/JID boundary counters and the current production compilation closure adapt the fixture without removing assertions.

## Required positive

qa/android_media_preview_test.py must complete both production API compilations and all 60 JUnit cases. One compilation uses the pinned real OkHttp 4.12.0 and DexKit 2.2.0 APIs; the lifecycle run uses deterministic HTTP scenarios. Android framework views/dialogs/handlers, BaseFeature, HookRegistrar, ViewHookDispatcher, HKDFv3, the privacy/JID model and preference bridge are compiled from production.

Decoder/audio routing, host database/class discovery, Xposed registration transport, contact lookup, text/tint resources and HTTP outcomes are declared fixture boundaries. Contact/JID lookups and Xposed preference reloads fail loudly and are asserted unused after every test. These results do not certify a real media download, decryption stream, host injection or physical decoder.

The baseline production media file in integration commit 6e9ae3ef638fa4e4abe5ac4a6ce0d9bf8014908b is identical to PR90's product merge-base. The port preserves the PR90 product bytes before import-only cleanup. The complete current source closure is compiled without patching BaseFeature or skipping Kotlin metadata checks.

## Required negative controls

Run qa/mutate_media_preview_lifecycle.py after the healthy gate. Every mutation must compile, execute all 60 cases and fail through assertions naming its intended behavior.

| Mutation | Required behavior detected |
|---|---|
| unbounded-progress | Bursts coalesce into the latest pending UI update |
| leaked-pending-bitmap | An unpublished decoded bitmap is recycled on dismiss |
| late-ui-registration | Callback registration serializes with cancellation |
| uncancelled-call | Dismiss cancels the active HTTP call |
| orphaned-replaced-temporary | A file created during identity replacement is removed |

Compiler, dependency, setup or timeout failures do not satisfy these controls. The mutation runner snapshots all compiled sources plus the auxiliary restart-constant source. Keep each result JSON, JUnit log, source hash and API compilation output.

## Product behavior

A preview owns its task, HTTP call, dialog, video callbacks, temporary file and unpublished bitmap. Replacement cancels the previous session, removes its queued task and limits the executor queue to one pending task. Delayed UI work checks session identity. Local host media is borrowed and is never inserted into the owned temporary-file slot. Closing a stale session cannot cancel or delete its replacement's resources.
