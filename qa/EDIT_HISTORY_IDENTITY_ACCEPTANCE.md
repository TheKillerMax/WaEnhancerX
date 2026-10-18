# Edit history: adapter receiver, cache namespaces and original-text lookup

Three independent code paths could associate edits with the wrong message:

1. The getView hook is installed once per adapter class, but its callback captured
   the first adapter instance. Another conversation using that class still read
   items from the first adapter. The callback now reads the invocation receiver.
   Successful row-only recycling also clears an earlier waex_key_id fallback;
   an independently extended fixture exposed this adjacent stale-key path.
2. History cache keys used both raw message keys and numeric row IDs in one String
   namespace. A message key `77` could receive row 77's history. Keys now have
   separate `key:` and `row:` namespaces; persisted database values are unchanged.
3. A missing or blank-text message-key lookup fell back to a reflected row ID.
   The store now resolves the database row from that key before any FTS fallback,
   rejects absent/ambiguous keys and never substitutes the unrelated numeric ID.

Run `python3 qa/test_edit_history_identity.py` and
`python3 qa/test_edit_history_adapter_binding.py` with JDK 17+ and Kotlin CLI.
The first compiles the whole actual EditMessageStore with explicit Android DB
doubles and covers separate caches, caller copies, missing/duplicate keys,
empty/null text, schema/query failures, verified FTS, row-only compatibility and
database-handle closure. The second compiles the verbatim extracted production
getView callback with distinct same-class adapters, including successful row
recycling. This does not execute the whole host hook or Android views.

The original production store compiles but fails both the cache and lookup
scenarios. Compiled regressions restoring shared cache names and unverified FTS
also fail. The original callback compiles but fails the second-conversation
assertion. Initial fixture failures (Kotlin nullability versus Java platform
types, and a substring assertion matching key_id) were corrected in the test
doubles; they were not production failures.

On authorized builds, edit permitted test messages in two private/group chats,
switch repeatedly between conversations whose adapters share a class, reuse rows,
reopen history and restart the host. Compare exact message versions with the
correct participants. Exercise empty captions, missing original rows, the actual
message/FTS schema, IO failures and concurrent edits. Confirm original host edits
still execute and no protocol/receipt behavior changes.

This is not complete chat-scoped storage: the historical schema still stores
key_id without chat/from-me identity, and other host key resolvers still require
validation for duplicate keys. Row-only fallback still relies on its supplied
row ID. The follow-up below covers local recycled-binding and persistence-failure
contracts; full host/device acceptance remains required. No database migration, deletion or retroactive
repair of already misattributed history is performed. No device performance or
cross-process SQLite guarantee is inferred from these local tests.

## Follow-up: bounded chat work and confirmed persistence

The getView callback now binds by the stable key without querying msgstore.db for
an otherwise unused numeric ID. Row-only compatibility retains its reflected ID.
A new token is installed before the enabled gate on every valid row result. A
listener from an earlier binding cannot open its predecessor's history after a
failed/unsupported bind or an off -> recycle -> on sequence. The click callback
also checks the current feature setting. The global attachment fallback retains
both direct-label and identified-ViewGroup paths, but skips subtree scans when
there is no identity it could bind.

EditMessageStore now treats query failure as unknown history and db.insert < 0
as failed persistence. A transition commits all its versions in one SQLite
transaction before publishing cache data. Failed/ambiguous completion invalidates
both known key and numeric cache entries. Original text is prefetched outside the
private write transaction; persisted history is then rechecked inside it. This
avoids introducing a private-database -> host-database lock order. Provided
original text needs no preliminary database read. Failure recovery rereads the
authoritative database and does not display candidate versions as confirmed.

The cache keeps at most 500 histories, 4,096 version records and 1,048,576 UTF-16
units across text, message keys and cache keys. Oversized histories remain intact
in SQLite and are returned in full, but are not retained in the cache. LRU eviction
only releases cached copies. These limits bound retained cache payload and record
count, not Android process RSS or the full history dialog's transient allocations.

EditHistoryDiff preserves the complete old and new text. Ordinary short ASCII/BMP
text still uses the existing LCS tie policy. Its table contains at most 90,601
integer cells; text longer than 8,192 UTF-16 units bypasses tokenization. Text above
the work budget uses a common prefix/suffix and a removed/added middle region.
Highlighting can therefore be coarser, while neither version is truncated. Emoji
use whole word tokens in the LCS path; the large-text path keeps UTF-16 surrogate
pairs in one chunk. Merging uses a StringBuilder instead of repeated growing
String concatenations.

Run the two suites above and `python3 qa/test_edit_history_diff_budget.py`. The
workflow requires all three. The store fixture covers rollback, retries, null or
partial cursors, failed reads/commit, cache alias invalidation, a competing write
between prefetch and transaction, host/private lock ordering, and memory-budget
eviction without truncation. The extracted production getView/click/attachment
callbacks cover 10,000 bindings with zero canonical DB queries and 10,000
unidentified attachments with zero subtree searches. The diff fixture checks
both reconstructions, an independent one-row LCS oracle for 1,000 generated short
cases, Unicode boundaries and large inputs under a 64 MiB JVM heap limit.

The previous production code compiles but fails targeted insert/cache/query and
callback controls; its 6,000-word comparison exhausts that same test heap. This
is a controlled JVM comparison, not a claim about measured Android FPS or a
proof that every lag report is resolved. The doubles count actual callback
boundary calls; they do not execute Android SQLite, View rendering, reflection
selection, transport or Xposed installation.

Further device acceptance must stress long histories, concurrent host callbacks,
SQLite failure/rollback, multi-account changes and screen recycling while toggling
the feature. Profile UI frames and database work on authorized Debug and optimized
Release builds. Opening the history dialog still performs a synchronous store
read and constructs all returned version cards, and the existing writer still
uses its original unbounded work queue. Reflection discovery is host-dependent,
the schema still lacks full chat/from-me identity, and existing positive caches
do not receive cross-process invalidation. The change does not recover history already misattributed or edits
not observed by a validated hook.

## Follow-up: reject demonstrated numeric identity conflicts

A keyed history containing distinct positive `row_id` values is now ambiguous.
The store returns no combined history and does not write into it. A requested
positive row ID that conflicts with the sole stored positive ID is also rejected,
including on cache hits. The internal query returns unknown rather than an empty
list, so a conflict cannot authorize a new first version. The transaction's
authoritative recheck covers a different-row writer arriving after prefetch.
Existing rows are preserved; no migration, deletion or automatic repair occurs.

The positive ID check runs in the existing cursor loop. Cached histories retain
their actual positive ID, if any, and reject a contradictory request in constant
time without another SQLite query. Zero/nonpositive IDs stay unresolved: a caller
cannot promote them to its requested ID, and persisted unresolved rows are not
rewritten when a later positive row appears. This permits existing key-only
history behavior until the schema provides stronger identity evidence.

The store suite adds legacy mixed histories (both row orders and intervening
zero IDs), a second distinct-row writer, same-row retries/edits, a competing write
at transaction entry, unresolved rows and both write-filled and read-filled cache
paths. Its 10,000 contradictory cache reads perform zero additional DB queries.
These local checks demonstrate rejection of numeric contradictions. They do not
establish uniqueness by chat, sender or account, verify a reflected numeric ID,
or detect another process changing a history while a positive cache is retained.
The ambiguous legacy history remains unavailable through key-based UI until a
separate identity-aware migration or repair can establish its correct ownership.
