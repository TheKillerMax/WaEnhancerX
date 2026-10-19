# Preserve vault data after the capture-hook revert

The local-delete contribution temporarily advanced `waex_preserved_messages.db`
to schema version 3. Reverting that contribution restored a version-2 helper.
Android's default `SQLiteOpenHelper.onDowngrade` rejects 3 → 2. Because the store
catches read/write errors, an affected installation shows an empty vault and
cannot append new records even though its previous rows are still on disk.

The compatibility release advances the helper to version 4. Versions 2 and 3
have the same nine columns and differ in their UNIQUE key. Both remain readable
and writable by the restored store implementation. Their tables are deliberately
left intact: no rename, copy, DROP, index replacement, deduplication or data clear.
Version 1 retains the existing additive `sender_name` upgrade. Unknown future
versions still reach Android's default rejection; there is no blanket downgrade.

Fresh installations keep the restored `msg_id UNIQUE` schema. Existing version-3
files keep `UNIQUE(jid,msg_id,from_me)`, including records that would collide under
the older index. This is a compatibility allowance for two historical layouts,
not a change to host message selection or local-delete capture. Future schema
migrations must account for both layouts.

The public store model retains the logical message ID and additionally exposes
the existing SQLite `_id`. The vault maps that physical ID to its list key. This
keeps opposite-direction records and old nullable IDs individually displayable
without fabricating or changing message identities. The original insertion
behavior, including SQLite's row replacement rules, stays unchanged.

## Automated evidence

Run `python3 qa/android_preserved_store_test.py --out /absolute/new/output` with
JDK 17+, Kotlin and Maven. The script copies the complete production store and
contact policy unchanged, compiles them against Android's real API, and executes
21 JUnit cases on Robolectric 4.17 / Android API 24, 28 and 34. Each SDK covers:

- Fresh creation, persistence and model fields.
- Version-1 additive migration with previous row IDs and sequence retained.
- Version-2 table/index definitions, all row values, and autoincrement continuity.
- Version-3 opening and reopening with duplicate logical IDs across directions
  and chats; schema, all values, row IDs, and sequence stay intact.
- Version-3 append and replacement behavior without changing another tuple.
- Rejection of an unknown future version with schema, data and version intact.
- Stable physical row keys for duplicate and nullable logical message IDs.

`--source-root` can exercise an unchanged baseline against the same fixture.
`--deps` reuses pinned dependencies, and `--sdk-jars` runs with an already prepared
offline Robolectric SDK directory. Logs and source/dependency hashes are written
for each run. The CI job requires all 21 cases and uploads its text evidence.

On main `b7d2ae44` (the production store is identical at `1c6dae5e`), all sources
compile and the 21 cases execute; the nine version-3 assertions fail because the
store returns no records. This is separate from the unrelated source-QA import
failure after the feature reverts.

## Runtime scope

These are real Android database-helper lifecycle tests with real SQLite files
and synthetic records. They do not execute WhatsApp, the local-delete selector,
LSPosed injection, or the full Compose vault screen. The screen's small key-mapping
change is reviewed separately. This patch does not restore the rejected strict
selector or claim to repair all missing Deleted Stories/local-delete captures.

Device acceptance should update an installation with a nonempty version-3 vault,
confirm its previous records remain visible, capture a new local-delete message
using the restored hook, and reopen the manager. Do not clear app data for this
check. Installing an older helper afterward is still subject to that older
binary's own downgrade policy.
