# IG status row loading

## Behavior covered

`IGStatusAdapter.getView()` previously resolved contact names, opened the status
database, read avatar files, decoded full images and created circles at source
image size while binding a row. Those operations ran on the caller used to bind
the horizontal list. A slow provider or large image could therefore block a
scroll or layout pass.

Row binding now sets a bounded placeholder and queues read-only loading on two
workers with at most 32 waiting requests. Saturation rejects work and retains the
placeholder; it never executes the loader on the caller. Recycling and detaching
a row remove queued work and posted deliveries. An already running provider or
decoder call may finish, but its result cannot update the cancelled row.

The queue stores a weak target. The production work lambda captures application
context and immutable row inputs, without retaining an Activity, adapter or view.
A ticket identity check prevents an old contact from replacing a newer binding.
An unfinished row reloads after attachment. Successful rows retain their current
image through a detach/reattach until a new binding or data notification.

File and blob decoding first inspect dimensions. Power-of-two sampling limits
the requested decoded longest edge to four times the target row size. The final
centered circle is 62 dp, clamped to 1–512 pixels, including non-bitmap drawables.
This bounds requested pixel allocations; native codec overhead and the database
blob itself are not measured by the test doubles. The placeholder shares its
pixels within the adapter and is rebuilt if density or night mode changes.

Avatar lookup uses `ContactIdentityPolicy` to preserve identity namespaces. An
exact `<jid>.j` remains valid for a canonical LID, group or phone JID. A numeric
`Profile Pictures/<number>.jpg` fallback is available only for a phone JID. The
same digits in a LID do not authorize a phone alias. This also removes the
redundant second lookup of the same canonical phone avatar file.

Containers are registered through weak references under their existing lock and
collected entries are removed with the iterator. Data replacement and snapshot
capture share the items lock. An adapter uses one snapshot for count and binding,
refreshing it when notified. Each container coalesces outstanding refresh posts;
the pending flag is cleared before notification so a concurrent or reentrant
update can schedule the latest pass. Detachment removes its posted refresh and
reattachment requests current data.

## Automated evidence

Run with JDK 17 or later:

```bash
python3 qa/test_ig_status_loading.py
```

To retain logs and demonstrate the original regression using a main checkout:

```bash
python3 qa/test_ig_status_loading.py --out /tmp/ig-status-qa --baseline-root /path/to/main-checkout
```

The suite compiles the **complete production adapter and container view**, plus
the actual Java worker and thumbnail policy. Explicit Android and host doubles
record thread affinity, decoder options, allocations and callback scheduling.
Registry and snapshot bodies are copied verbatim from the hook into a compile
harness; DexKit and Xposed installation are outside that harness.

The candidate passes 57 adapter/view checks and 228 executor/pixel-bound checks:

- Contact and own-status binding performs no database, file, name or decoder I/O
  on the binding caller; the completed name and avatar reach the row through the
  supplied UI dispatcher.
- Rebinding A to B while A is blocked preserves B after A completes. Detaching
  active or queued rows prevents delivery, and reattachment reloads the latest
  row. Posted callback cancellation removes its pending result.
- A saturated real executor rejects work without running it on the caller.
  Cancelling a queued request frees capacity. Clearing the production weak target
  deterministically skips its loader, without relying on GC timing.
- A production row lambda inspected while actually queued contains no Activity,
  view or adapter capture. A rejected UI post releases its pending result.
- Both decoder overloads request bounds before pixels; invalid dimensions stop
  before allocation. Portrait, panorama and extreme integer dimensions obey the
  power-of-two sample ceiling. The circle uses row dimensions and centered scale.
- Placeholders reuse pixels and respond to theme/density changes. Adapter count
  and rows retain the same snapshot until notification. Invalid positions clear
  a recycled click target.
- A LID cannot borrow a same-number phone avatar or phone cache, while its exact
  avatar remains available. Groups also reject phone caches, canonical phones
  retain that fallback and unsupported identity suffixes cannot select a file.
- A burst of 100 updates posts once, an update during notification gets its next
  pass, and detach/reattach and failed-post recovery preserve the newest refresh.
  Duplicate fragment registration replaces the weak entry and collected entries
  are removed safely.

The baseline at `a605ee6a96725d065fd838a6f058c47f9dde6a7f` compiles with the same
harness, then fails the assertion `binding performed I/O on the main caller`.
Compilation failure does not count as rejecting that regression.

The added LID assertion also reproduces the separate avatar mismatch on the
first async candidate: with only a same-number phone avatar on disk it fails
`LID must not borrow same-number PN avatar without a verified alias`. After the
namespace check, the same fixture passes all six identity/fallback scenarios.

## Practical limits and integration

These are control-flow and allocation-contract checks with doubles. They do not
build an APK, execute Android's actual codec/Canvas, emulate WhatsApp's database,
validate a DexKit selector or measure frame times on a device. The existing
native status schemas and navigation behavior are preserved. In particular, the
own-status check when a user **taps** its row still follows its existing query
path; this change removes I/O from repeated row binding.

Under sustained saturation a row may retain its placeholder until its next bind
or attachment. The worker does not forcibly interrupt an active database/provider
or native decode when a row goes away. Its completion is discarded instead.

The 32-entry limit applies to waiting worker requests. UI messages have no
separate global quota: each live holder owns at most one ticket/delivery.
`HorizontalListView` fills the visible width and passes removed rows through its
recycle queue; `removeViewInLayout()` detaches them, cancelling their pending
work/delivery, and a rebind cancels the old ticket again before requesting a new
one. This bounds retained results by current holders in ordinary scrolling, not
by every status in the data set. Multiple simultaneously live containers can
have their own holders. The callback keeps its target weakly and releases its
result after delivery or cancellation. Real Android detach/layout behavior still
belongs to the device acceptance below.

When combined with the localization branch, preserve its existing `UiText` calls
at the corresponding labels and navigation messages. The harness supports the
bridge with fallback text, while resource ownership remains covered by the
separate resource QA. Source/JVM QA registers `qa/test_ig_status_loading.py` and
requires it and its fixtures whenever `StatusRowWorkQueue.java` is present. The
broader change that makes all existing suites required remains in the CI branch.

Device acceptance still requires scrolling many contacts, switching tabs and
recreating the Activity while names/images are slow, and verifying current names,
avatars and navigation with both public application IDs and supported host APKs.
