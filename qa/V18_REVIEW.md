# V18: checked manual saves and explicit presence invalidation

Continuation of V17 on upstream `4bbe5cb02ce2fe924136a9579d2582c1a4818643`
and combined fork `562da7d08fc3926b2463c29c064815f79a80fcff`.
These are reviewed source changes, not an APK release or completed LSPosed acceptance.

## Manual setting (existing #35)

The `seentick` branch of the actual Styles update lambda used a void setter,
then reread memory as if persistence had succeeded. It now uses the checked
public STRING writer from #39, updates the visible toggle only on success,
and reports `Unable to save setting` on failure. The standalone #35 carries
an identical copy of that checked writer and schema predicate so it does not
require #39 to compile; the combined source retains one definition of each.
The toolbar/overflow modes, explicit toggle semantics and Pro gate are unchanged.

The new JVM regression executes the production lambda and preference manager
with explicit Android/Compose substitutes and separate in-memory/durable maps.
Sixty scenarios cover six starting values, two requested values and five write
outcomes, including editor/commit exceptions, false commits, memory-before-disk
failure and retries. It rejects V17 behavior after compilation. This does not
simulate real flash I/O or establish persistence across actual Android restarts.
The existing typed-editor guard accepts either historical or checked manual
wiring because those PRs are independently reviewable; the new manual regression
requires the checked path and still rejects false-success behavior.

## Presence lifecycle and queued notifications (existing #41)

The selected handler must additionally invoke a three-argument void method with
the exact disconnected diagnostic anchor. Read-only instructions of the supplied
host establish event 1 as connecting and 4 as disconnected; event 3 is connected,
not disconnected. Those transitions clear process-local presence observations.
Only an unavailable (`what=5`, `arg1=64`) envelope with an explicit `deny` and a
valid contact JID invalidates that identity. Unknown payloads remain ignored.

A denial creates an unknown tombstone with no last-seen timestamp; row replay
includes it when choosing among explicitly linked identities. The dot and text
are cleared, not rendered as an offline/last-seen fact. Retention follows last
observation, not UI reads: an older alias cannot survive eviction of its newer
tombstone merely by being repeatedly read. The 2,048-entry limit is preserved.

Online toasts retain the exact transition token returned by the update operation,
not a later reread. Both the lookup worker and the final UI queue check that the
same identity/transition remains online; the latter also rechecks the option.
Repeated observations do not create additional toast transitions. A reentrant
listener cannot steal a later transition token. Other toast routes keep their
existing behavior and original host messages are never cancelled or mutated.

## Verification scope

The source/JVM tests include the 60 manual scenarios, 107 incoming-event checks,
21 queued-callback scenarios, and 21 cache/invalidation checks with 12,000
concurrent operations. Existing replay checks and all other merged regressions
must remain enabled. Fourteen controlled source mutations must fail behavioral
assertions after compilation, not merely fail to compile.

The renderer fixture adds six scenarios to the existing nineteen, on API 28,
34 and 36 with Robolectric 4.17 native graphics (75 executions when successful).
It tests denial/global reset, prior aliases, pending refresh and actual bitmap
pixel removal. The fixture target SDK remains 28, distinct from those runtime
API levels. Fifteen unsafe renderer/cache variants are checked on API 34.
Dependency download, syntax, query construction, JVM and renderer results are
recorded independently by the validation job; a plan is not evidence of a pass.

## Boundaries still open

No arbitrary presence TTL is introduced: silent transport loss outside the
reviewed lifecycle messages, general freshness and authoritative server last-seen
remain unresolved. Row aliases come from the existing reflective host path;
this change does not certify those identity/subscription/binder contracts.
Queued toast cancellation checks its exact event identity, not unverified
cross-identity equivalences. A state reset does not guarantee every host version
emits the reviewed lifecycle messages. Native DexKit matching is not exercised
by compiling a query or inspecting equivalent instruction predicates.

Audio/view-once classification and mixed played-receipt batches remain open.
The further instruction review did not justify replacing them with guessed
integer fields or reinterpreting `playedSelfFromPeer`. Sending issue #38,
Binder/certificate trust, long-session memory, actual databases, 16-KiB native
compatibility and all 93 feature acceptances still require their own evidence.
No APK, private licensing module, signing material, entitlement decision or real
user configuration is altered. The supplied host has an Android Debug signer
and is not certification of an official WhatsApp distribution.
