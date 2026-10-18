# Forwarding flag preservation after the October 17 revert

This follow-up targets `f6ec7d4e6f47a246ebb413848d66358217fa9c08`.
PR #53 was merged, then its implementation was reverted in
`395a9eca42912ee1eb79a5be8653f4b277746c1c`. The subsequent commit
`5276882a3be4d4f2fee1555801cb14cdc4e47630` restored an ambiguous numeric
method selector and the canonical/legacy preference OR.

## Observed contract and chosen scope

Local inspection of the supplied WhatsApp 2.26.40.76 sample (SHA-256
`593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4`) traced the
`chatInfo/incrementUnseenImportantMessageCount` anchor to an invocation of a
one-long-argument, void method on the message object. Its four instructions
read a long field, OR the input bits, write the field, and return. This is a
flags operation, not evidence of a forwarding-score setter. No host code,
APK, message data, or extracted bytecode is part of this contribution.

The previous callback replaced positive arguments with zero. When forwarding
caller discovery returned no classes, its guard accepted every call. That can
suppress requested flags. An unrelated string anchor, a numeric parameter,
and a void return type do not establish the semantics needed to mutate it.

The selected correction removes that interception. A new candidate selector
would require independent host contracts and device validation. Disabling
all forwarding behavior would remove the narrower supported persistence
path unnecessarily. The retained path only adjusts an existing positive
integer `forward_score` in an insertion into the exact `message_forwarded`
table. It copies `ContentValues` for SQLite, retaining the caller's original
object, origin metadata, other values, absent fields, and unsupported types.
An explicit canonical `false` takes priority over legacy `hidetag=true`.

This deliberately does not promise that every in-memory or already-rendered
forwarded label disappears. It also does not establish that this bug caused
every community report of messages remaining pending.

## Reproducible checks

```sh
python3 qa/test_forwarded_metadata_scope.py
python3 qa/mutate_forwarded_metadata.py --out /tmp/waex-forward-negative-controls
```

The test compiles the complete production Kotlin hook. Explicit Android,
Xposed, and DexKit substitutes drive its actual registration and callbacks.
A synthetic flags OR method is selected by the original algorithm while
both forwarding-caller queries return empty. The original main source
compiles under the same fixture, then loses the requested flag bits. The
corrected source preserves them without numeric interception.

All three supported SQLite insertion callbacks are exercised with canonical
and legacy settings, denied/corrupt reads, unrelated tables, absent/null
fields, positive/zero/negative scores, alternate types, preserved origin,
caller ownership, and incomplete callback arguments. Six unsafe variants
must compile and fail a named behavioral assertion. A compile failure or
timeout does not count as successful detection.

CI requires this test whenever `HideForwardedTagHook.kt` exists. The
requirement no longer depends on a literal in the corrected implementation,
so reverting that implementation cannot silently retire its regression test.

## Remaining acceptance

Build with the authorized private dependencies and signing configuration.
On supported official WhatsApp and Business versions, compare enabled and
disabled behavior while sending original and forwarded text/media. Confirm
delivery, edit/revoke state, database integrity, and forwarding labels after
restart. Record the host and module versions and option values. No account
traffic, Android installation, Binder/LSPosed execution, or signed full APK
build was performed by this source-level check.
