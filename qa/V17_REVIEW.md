# V17 proactive review: presence rows and played dispatch

Review date: 14 October 2026 (America/Santiago). Experimental source changes, not an APK release.
Base upstream: `4bbe5cb02ce2fe924136a9579d2582c1a4818643`.
Prior combined fork: `e5ee3d87d56d7694528e3a1ed3d999e22c8a4aee`.

## Presence rows (follow-up in existing PR #41)

The event receiver fixed by #41 is not the whole online-dot pipeline. The renderer previously recovered cached state only by the row key, although live events used registered aliases. It also laid out an overlay without measuring its children. The corrected renderer replays explicitly linked cached identities, orders observations by process-local revisions, handles late/conflicting aliases, invalidates delayed binds when rows are recycled, clears stale decorations on invalid binds, coalesces observation bursts, measures after visibility changes and follows host layout direction. Overlay values are weak because their Android parent may retain the host row.

The production store preserves its 2,048-state bound, listener failure isolation and transition return value. Repeated observations advance revisions and notify render listeners without producing a new toast transition or changing the previous transition timestamp. Explicit identity links are supplied by the existing host path; this change does not prove that every reflected host identity is correct and never invents a phone/LID equivalence by prefix.

`qa/android_presence_row_test.py` extracts actual renderer bodies and compiles the production store against Robolectric 4.17 with native graphics. Nineteen scenarios ran on API 28, 34 and 36: **57/57 passed**. They include measured dimensions and an actual rendered bitmap center pixel, not only visibility flags. Two regressions run on the prior source across those APIs fail all six behavioral assertions. Twelve deliberately unsafe variants fail Android 14 assertions. Verification run: https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38656031140.

The initial run failed three RTL cases because the manifest-free test application did not enable RTL. The fixture now explicitly enables RTL, asserts the host direction and retains the original overlay assertion. No production check was disabled. The test harness uses Android framework classes but is not a physical device, the actual WhatsApp row binder, ART/LSPosed or a full application build. Its target SDK is explicitly 28 for the manifest-free fixture; its three runtime API levels are distinct.

`qa/test_presence_state_replay.py` adds 24 JVM checks, 14 source guards and 32,000 concurrent observations. A source guard or a counted observation is not an independently certified feature.

## Played receipts (follow-up in existing PR #40)

The legacy `sendClearDirty` class search identifies a multi-purpose dispatcher. Its broad one-reference-argument hook also selected a method that constructs `SendMediaErrorReceiptJob` in the supplied host. With played privacy enabled, the old callback could suppress that unrelated media-error path. This is a separate method-selection defect from #40's original status-job lifecycle correction.

The new selector requires a unique public instance `void(Set, boolean)` method that invokes the two-argument `SendPlayedReceiptJobV2` constructor containing the exact `played-receipt-v2-` literal. It does not pin obfuscated names. Runtime method/callback shape and cached descriptors are checked, and missing/ambiguous matches report incomplete privacy coverage instead of installing broad hooks. The existing played-batch suppression decision is retained; neither the caller-owned set nor the peer flag is rewritten.

`qa/test_played_receipt_dispatch_contract.py` executes 51 checks using the production installer/resolver/classifier and a production shape policy with explicit JVM doubles. The read-only supplied-host instruction inventory found one constructor and one matching caller. Its second Boolean represents `playedSelfFromPeer`, not a view-once discriminator. No native DexKit lookup or live message delivery has been established by that static inventory.

## Explicit review frontier

- Audio versus view-once classification and mixed-batch granularity are NOT repaired by the scope-only played change. The legacy classifier and first-element decision still require a separate verified media-kind contract.
- Presence cache expiration, transport disconnect invalidation and denied-presence handling remain open. The stored transition time is not certified server last-seen information.
- Row-binder selection, reflective identity/subscription resolution and actual host layouts are not certified by the extracted renderer tests.
- Manual `seentick` persistence, other void preference setters, remaining DEX anchors, receipt transport, Binder/certificate trust, long-session memory and database migration still require their own acceptance.
- A complete public-source heuristic scan and 93-entry review ledger are triage aids, not proof that every flagged site is defective or that every catalog entry works. Existing regex/source tests are not measured line/branch coverage.
- No private licensing source, signing checks, Pro decisions, real user configuration, upstream main or proprietary APK was modified. The supplied WhatsApp APK has an Android Debug signing identity; it is not official-distribution certification.
- The blocked-sending issue #38 and online/delete-toast substitution remain without causal device reproduction. Do not close either on source, Robolectric or JVM evidence alone.

## Integration

#41 overlaps #17's presence store/notification work and #25's renderer diagnostics. Retain bounds, sanitized logs and the incoming event contract. #40 overlaps #35 in HideReceiptsHook; retain exact-recipient/message-ID allowances, Ghost Mode precedence and constructor capture. The reviewed combined fork retains both sets of changes rather than replacing whole files with an older standalone PR base.

Run source/JVM suites and the Android row runner on the exact combined tree. Use two authorized test accounts for actual sending, privacy, presence, row recycling, reconnection and restart acceptance. A working test fixture does not certify all 93 catalog entries.
