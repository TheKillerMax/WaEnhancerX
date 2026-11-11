# Message Device Source: listener ownership and row binding regression gate

## Scope and source identity

This QA suite targets `MessageDeviceSourceHook.java` on upstream/fork `main`
`da0ab21533029173b126ce69e2032ee9378e062e` (WAEX 2.0.6). It continues
the listener/row-lifecycle analysis from 2026-11-10. Upstream PR #111 is now
merged; the present candidate preserves its `DeviceJidParser`, incoming-stanza
argument resolution, and `date` / `date_wrapper` resource lookup. The candidate
is stacked on `fix/device-source-id-main-20261111`, which fixes independent
message-ID extraction defects.

The baseline is read directly from the pinned Git commit by `git show`. The
candidate is read from the working tree, so the suite always records the exact
SHA-256 of each input. Original APKs v2.0.4 are not test inputs.

## Regression mechanism

1. Invalidate `convertView` **before** the host's `getView()` body can update
   text, and defensively invalidate the returned row / distinct old view
   afterward. This applies even on disabled settings, null items, lookup
   failures, unknown messages and non-row results.
2. Retain a per-row binding generation and weak references to annotated
   `TextView`s, including a secondary view that was later detached. Avoid
   references from Xposed additional-field values that would keep their own
   weak-map keys (and parent Activity) alive.
3. Refuse delayed device resolutions when the generation, row, anchor, current
   message ID, or current preference no longer matches.
4. Install a device click listener only if its slot is unoccupied or still
   owned by this hook. Replace an owned listener with a **new identity** on
   rebinding; captured stale callbacks must never be reactivated.
5. Clear only WAEX-owned listeners and annotations. Preserve host/transcription
   listeners and explicit host clickability changes. If listener ownership
   cannot be inspected, invalidate the callback and avoid speculative mutation.
6. Restore annotation text only when the displayed value exactly matches the
   previous WAEX rendering; otherwise leave host text untouched. Store only
   immutable `String` snapshots. Guard WAEX `setText()` calls against reentry,
   and invalidate secondary annotations after independent host text updates
   until a future adapter bind verifies their relationship again.

## Repeat the A/B and negative-control gate

With Python 3, a JDK that includes `jdk.compiler`, and the pinned Git commit:

```bash
python3 qa/device_source_lifecycle/verify.py --out /tmp/waex-device-source-gate
python3 -O qa/device_source_lifecycle/verify.py --out /tmp/waex-device-source-gate-optimized
```

The gate extracts the **actual Java methods and nested classes** from the
selected source, compiles those fragments against strict, explicitly controlled
Android/Xposed/host adapter/store/asynchronous-executor doubles, and executes:

| Suite | Pinned baseline | Candidate requirement |
| --- | ---: | ---: |
| Listener ownership | 9 pass / 17 fail | 26 / 26 pass |
| Adapter binding and callbacks | 4 pass / 26 fail | 30 / 30 pass |
| Eleven independently broken variants | Not applicable | All rejected by behavioural failures |
| Weak-key retention model | Deliberately strong graph remains retained | Production weak-view graph collected |

The baseline failures are expected negative evidence, **not** 43 separate
verified WAEX bugs. Each mutation must compile and execute; a compilation
failure is not accepted as a detected regression. The independent fixtures
exercise identity, stale async completions, different/same message IDs,
disabled settings, recycled and detached rows, clickability, and foreign click
actions, preservation of legitimate emojis, secondary host edits, updates inside
`getView()` itself, and reentrant
`setText()`. The retention fixture compiles the exact row-binding class and tracking
method into a model of Xposed's global `WeakHashMap`; it tests both a collected
candidate and an intentionally retained strong-reference graph. The gate writes
method extraction ranges, input hashes, commands, case-level outputs, and
negative controls into `RESULTS.json`.

For #111 compatibility the binding fixture also compiles the actual
`DeviceJidParser` production implementation. CI must fetch the pinned main
ancestor because the A/B baseline is read from Git rather than reconstructed
from candidate code.

On the current Linux host, OpenJDK 21 has `jdk.compiler` but no `lib/ct.sym`;
the scripts explicitly use `-source 17 -target 17` instead of unavailable
`--release 17`. This does not prove Java 17 library API compatibility. Run with
an intact JDK 17 and `--release 17` before treating that dimension as verified.

## Acceptance gaps and operational risks

- No full `:app`/`:licensing` compilation, installation, Android/LSPosed or
  WhatsApp callback was executed. Private `:licensing`, signing configuration
  and host access are required for full candidate acceptance.
- Listener ownership inspection uses Android's non-SDK
  `View.mListenerInfo.mOnClickListener`. Access may be restricted by Android;
  failure must leave foreign listeners untouched and may omit the feature's
  click toast. Test on the exact target Android/framework versions.
- The separate transcription button in current main does not demonstrate the
  older PR #111 transcript-listener collision. Its marker is guarded as a
  compatibility seam, not represented as a proven reachable bug.
- Runtime rendering, screen-reader interactions, correct device attribution,
  message identity extraction, adapter hook resolution and performance/jank
  remain `NOT_VERIFIED`. The setter hook is installed at module initialization;
  enabling this feature for the first time may require a target restart.
- If the host updates a secondary view outside `getView()`, this change removes
  its WAEX annotation and click action until another adapter bind. This
  deliberately prioritizes not showing a stale attribution over instantaneous
  reannotation; confirm the actual WhatsApp rendering order on-device.
- A follow-up Android test should inspect actual callback installation,
  deactivation and row recycling without sending any message or receipt. Live
  WhatsApp events require their own account/destination/operation authorization.

Useful primary contracts:

- [Android View source](https://android.googlesource.com/platform/frameworks/base.git/+/master/core/java/android/view/View.java)
- [Restrictions on non-SDK interfaces](https://developer.android.com/guide/app-compatibility/restrictions-non-sdk-interfaces)
- [XposedHelpers reference](https://api.xposed.info/reference/de/robv/android/xposed/XposedHelpers.html)
