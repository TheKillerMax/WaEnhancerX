# Local Delete-for-me capture and vault identity

## Source and host evidence

The reviewed WhatsApp 2.26.40.76 APK contains one method across all 13 DEX files
with both exact strings below and the instance signature
`(java.util.Collection, boolean, boolean): void`:

- `UserActionsMessageDeletion/userActionDeleteMessages ` (the final space matters).
- `UserActionsMessageDeletion/userActionDeleteMessages messagesToDeleteIncludingAssociatedMessages=`.

The observed method is `X.A0c.A07`. The Delete-for-me dialog's positive listener
reaches this action, which subsequently queues a worker. Production resolves the
semantic strings and signature; it does not embed that obfuscated name or a
Runnable switch discriminator. The old three discovery strings were absent in
this APK. Other WhatsApp versions still need their own discovery and device
checks; a supported-version declaration is not evidence for this hook.

## Behavior covered by source QA

Run `python3 qa/test_preserved_message_capture.py` with JDK and Kotlin CLI tools
available. The runner compiles the complete production hook, selection helper,
vault store and contact identity policy. Android, Binder, Xposed and DexKit result
objects are explicit doubles. Every database statement emitted by the production
hook and store runs against real SQLite through a Python worker.

| Contract | Exercised cases |
| --- | --- |
| Dedicated action | Both exact strings; unique result; missing/partial/prefix matches; static, wrong return and wrong parameter types; validation of cached methods |
| Selection | Direct and inherited typed keys, inherited message fields, instance ownership, static metadata, conflicting keys, unknown JID objects, blank IDs, and PN/LID namespaces |
| Capture | Same ID in another chat or direction, physical duplicate rows for a complete key, missing messages, type-15 placeholders, group names and sender names, and untouched original arguments/source rows |
| Scope | Nested callbacks, disabled inner callback, another thread, host return value and exception preservation |
| Database fallback | Canonical target `msgstore.db` only; no queries against another app/database; unknown chat/direction and unrelated table skipped |
| Vault | Composite `(jid, msg_id, from_me)` uniqueness, exact replacement, three distinct identities with the same message ID, and hook-to-vault integration |
| Upgrade | Canonical v1 and v2 databases upgraded to v3; v3 reopening; all nine columns and row IDs preserved; successful insertion of previously colliding identities |
| Failure recovery | An actual SQLite authorization error on the unmodified copy statement; transaction rollback preserves old version, schema and rows; retry succeeds |

The SQLiteOpenHelper double reproduces Android's documented transaction boundary
around `onUpgrade`. The SQL and migration methods are production code. This does
not execute Android's own SQLiteOpenHelper implementation. See the official
[SQLiteOpenHelper reference](https://developer.android.com/reference/android/database/sqlite/SQLiteOpenHelper#onUpgrade(android.database.sqlite.SQLiteDatabase,int,int)).

An optional `--dexkit-jar /path/to/dexkit-2.2.0.jar` compiles against the real
DexKit API and runs the capture/store cases. It omits the controlled native-result
fixture and does not execute native discovery. The runner supports a different
`--source-root`, comma-separated `--scenario` values, and `--evidence-dir` for
compiled baseline failures, source hashes and actual SQL traces.

## Device acceptance still required

Use separate debug and release builds with this commit, an existing populated
vault, and the target APK version recorded. Confirm that the dedicated action
installs after updating from a prior negative cache. Delete one received and one
sent text message locally, then a mixed multi-selection from a group and a LID
contact. Check that text, chat, direction, sender and timestamp appear in the
vault, and that WhatsApp performs the requested local deletion normally. Restart
both apps and confirm the captures and legacy rows remain available.

Repeat with the feature disabled and with a remote Delete-for-everyone event.
Confirm local preservation does not suppress the original deletion, change
message arguments, block sends, or classify remote revokes as local requests.
Measure a large selected batch on a device: capture and provider calls remain
synchronous before the host queues its worker, so this source suite establishes
no wall-clock latency or scrolling-performance claim.

The scope is synchronous and does not propagate into the host's asynchronous
delete worker. The existing provider/store API has no persisted-write
acknowledgement; a prepared request is not proof that the manager stored it. The
vault schema still lacks source-package/account identity, so this change does
not establish isolation between different WhatsApp accounts or packages. These
limits must remain visible when reporting acceptance.
