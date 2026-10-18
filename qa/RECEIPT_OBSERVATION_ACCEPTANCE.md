# Read receipt notification contract and acceptance

## Meaning of the notification

The message and status switches now describe a **read receipt received from a
contact**. They do not claim a new first view, a new host database row, or a
successful SQLite commit. A normal return from the reviewed host handlers does
not establish any of those facts. Replayed and reconciled receipts can reach the
same handlers, and the status handler can return without writing a row.

The existing preference keys remain `toast_viewed_message` and
`toast_viewed_status`. English and Spanish settings descriptions explain the
receipt semantics and grouping. Toast resources are supplied for English,
Spanish and Latin American Spanish. Toast language follows the host application
configuration. The formatted context must have the module package name and each
numeric ID must resolve to its full expected module string-resource name before
the string is read. Unavailable or foreign resources use explicit English
receipt text even if the numeric ID points to a valid string in another table.

## Host evidence behind discovery

The supplied WhatsApp 2.26.40.76 APK has SHA-256
`593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4`.
Its reviewed method bodies establish these relationships:

| Route | Required contract |
| --- | --- |
| Message identity | The unique zero-argument UserJid method with `FMessage/getSenderUserJid/key.id=` reads the final primary message-key field. A separate mutable key field is not used. |
| Message receipts | The unique `Collection` to `List` method with `upsertUserReceiptForMessage/INSERT_RECEIPT_USER` processes a five-field immutable receipt record. Its constructor takes DeviceJid, UserJid, FMessage, int and long. |
| Viewer | The record's UserJid has priority. Only when it is null is the validated DeviceJid's final UserJid field used. |
| Type | 13 denotes a read receipt; 5 denotes delivery and 8 playback. Read timestamps must be positive. |
| Own message | The final primary key supplies the message ID, chat JID and ownership flag. A receipt for another person's message cannot be announced as a receipt for your message. |
| Status | The unique four-argument status handler has the status key, insert-failure and `seen_timestamp` anchors. Its item contains the status key, which contains the base message key. Both ownership flags and the two IDs must agree. |
| Own-account status viewer | The handler's actual static self-account predicate and the matching provider field it reads are resolved together. True, unavailable or failed predicates cannot produce a notification. |

The implementation validates types and relationships again after discovery and
requires unique candidates. It does not contain version-specific obfuscated
class or field names. Missing or ambiguous contracts omit the corresponding
optional observer. Host arguments, return values and exceptions remain intact.

## Ordering, identity and work bounds

Before the original handler runs, the observer captures only immutable strings
and the message/status domain. It completes collection traversal before any
notification side effect. A traversal error or a batch exceeding 300 elements
discards the whole snapshot. The iterator bound is checked independently of the
collection's reported size. Unrelated objects are never stringified.

After the original returns normally, valid observations can reserve a pending
identity and queue name/resource lookup. Original handler exceptions suppress
notification. The result list and a normal void return are deliberately not
used as database acknowledgements.

Identity consists of domain, exact chat JID, message/status ID and exact viewer
JID. Receipt timestamps are not identity. PN and LID namespaces remain separate
unless the host itself supplied that exact JID. The process retains at most
2,048 delivered identities and 96 pending identities, including pending UI
delivery. Restart or eviction can allow a repeated receipt to be announced
again. This is not durable view history.

Name and resource lookup run on the shared single-worker executor, whose queue
holds at most 96 tasks. Displacing a queued receipt releases its reservation.
The rejection handler retries through `execute` once so a missing worker can
start; reentrant rejection cancels the new task. It never runs lookup on the
host caller. The production registry supplies an Application context, and queued
observations do not retain FMessage, status-item or Activity objects.

A cancelled task also carries a cancellation flag across threads. Worker
creation can throw after `execute` has already offered the task to the queue;
releasing its reservation alone would leave that abandoned task able to execute
alongside a legitimate retry. The task checks cancellation before lookup, after
lookup and at UI delivery.

The preference is rechecked before lookup, before posting and at UI delivery.
UI work consists of a cached preference read, a bounded monotonic throttle and
the Toast request. An identity becomes delivered only after `Toast.show()`
returns normally. Cancelled, rejected, disabled and failed tasks remain eligible
for a later receipt retry. The 1.5-second per-viewer/domain throttle can group
nearby receipts; a failed Toast can retry after that interval. Neither posting
nor a normal Toast call proves that Android visibly displayed the notification.

## Source-only checks

Run with Python 3 and JDK 17 or newer:

```sh
python3 qa/test_receipt_observation.py
python3 qa/mutate_receipt_observation.py /tmp/waex-receipt-mutations
python3 qa/test_notification_memory.py
python3 qa/test_presence_event_contract.py
python3 qa/test_presence_invalidation.py
```

The receipt suite compiles the actual policy, reflection model, dispatcher,
throttle and resource-text helper. Six installer/callback declarations are
extracted verbatim from the production hook and compiled against explicit
Android, Xposed, DexKit and host doubles. It also uses real Java thread pools for
saturation, shutdown, missing-worker behavior and a worker-creation failure after
queueing. The separate mutation command requires fourteen unsafe variants to
compile and fail Java behavioral assertions.
A Python assertion or Java compilation error is not accepted as mutant rejection.

These checks do not execute DexKit's native matcher, Android resource resolution,
WhatsApp, SQLite, LSPosed or UI rendering. Full Android compilation and device
acceptance remain separate gates.

The new selector declarations can also be compiled against the project's real
DexKit dependency rather than matcher/result doubles:

```sh
python3 qa/compile_receipt_dexkit_api.py --dexkit-jar /path/to/dexkit-2.2.0-classes.jar --kotlin-stdlib /path/to/kotlin-stdlib.jar
```

This separate check prints dependency and source hashes and uses actual DexKit
query, matcher and result types. Android context, Xposed and the project's search
engine remain compile-only stubs; the native bridge is not executed.

## Device acceptance before declaring the feature fixed

Use accounts and devices under the tester's control. Record the manager commit,
APK variant, target package/version, Android version and LSPosed version. Verify
debug and optimized release independently.

1. Exercise all four combinations of the two switches. A normal message read
   must retain message wording even with status alerts enabled. Delivery and
   playback alone must not produce a read receipt alert.
2. Exercise own direct and group messages with PN and LID viewers, the validated
   device fallback, and a message authored by another participant. Confirm the
   contact and message/status wording. Do not infer PN/LID aliases by string
   conversion.
3. Exercise an own status read by another account, own-account/linked-device
   observations, and a status authored by someone else. Confirm that unknown
   self-account information suppresses the optional alert without changing the
   host operation.
4. Re-deliver the same receipt and an older timestamp, then read a different
   message in another chat. Confirm duplicate grouping, independent identities
   and resumed alerts for new receipts after the grouping interval.
5. Disable the relevant switch while a lookup or UI delivery is pending.
   Confirm no stale alert, then re-enable and deliver a fresh retry. Repeat with
   a saturated lookup queue and a temporarily unavailable name lookup.
6. Check English, Spanish and Latin American Spanish, including a host locale
   change while the process remains alive and unavailable module resources.
7. Confirm ordinary send, receive, group read indicators and status behavior
   continue normally. Measure scroll and send latency under a controlled burst
   with alerts off and on; the source bounds are not a measured device-speed
   improvement.

No SQLite success, first-view timing or complete notification coverage should be
reported from these tests. Observing a valid incoming read receipt is the
feature's explicit, reviewable boundary.
