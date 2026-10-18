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
row ID. Unsupported/failed row binding and insertion failure handling remain
separate acceptance concerns. No database migration, deletion or retroactive
repair of already misattributed history is performed. No device performance or
cross-process SQLite guarantee is inferred from these local tests.
