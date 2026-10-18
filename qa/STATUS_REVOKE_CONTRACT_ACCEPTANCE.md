# Status revoke contract and playback mapper acceptance

## Defects addressed

The source baseline is `f6ec7d4e6f47a246ebb413848d66358217fa9c08`.
Static inspection of the supplied WhatsApp 2.26.40.76 host APK
(SHA-256 `593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4`)
established these contracts:

1. The status manager method selected by the old first-parameter search has
   `(revokeKey, targetKey, boolean incoming)` parameters. It uses the **second**
   key to look up and revoke the original status. The first key identifies the
   revoke event and can be null. Recording the first non-null key can therefore
   mark the revoke event instead of the story.
2. That method returns a non-null enum. One receiving caller passes it to a
   dispatcher whose first operation is `Enum.ordinal()`. The old generic
   `setHandledResult()` returns null for enum results, violating that caller's
   precondition. This is a static contract defect reproduced with a compiled
   caller fixture; no device crash is claimed to have been captured.
3. The playback-mapper string anchor matches both a real mapper and a
   bridge/synthetic method that always returns null. First-match selection
   admits the unusable candidate. The two candidates are proven; which candidate
   a particular device selected has not been observed.

The direct-call inventory was checked across all 13 DEX entries. Incoming
receipt and orphan-replay callers pass `true`; asynchronous local deletion
callers pass `false`. Two incoming callers bypass the manager's anchored void
wrapper, so intercepting only that wrapper would leave them unresolved.
The status key has exactly one instance String ID and one primitive boolean
ownership field across its class hierarchy. Its constructor and labelled
`toString()` agree on those meanings.

No proprietary host implementation or APK is included in this change. Host
class, method and field names are not hardcoded in the production resolver.

## Result policy and its inference boundary

The inspected enum has these named outcomes:

| Native outcome | Receiving caller | Orphan cleanup |
| --- | --- | --- |
| `STORED` | Success | Consumed pending revoke is eligible for removal |
| `STORED_ORPHAN` | Success | Different from the `STORED` cleanup branch |
| `FAILED_TO_STORE` | Error | No successful-consumption cleanup |
| `DIDNT_STORE` | Separate no-store path | No successful-consumption cleanup |

For an explicitly enabled incoming preservation action, this patch deliberately
acknowledges the suppressed revoke with the host's `STORED` constant. This is a
module policy inferred from the verified caller behavior: it retains successful
consumption and cleanup while skipping the destructive status mutation. It does
**not** assert that the module stored a host revoke placeholder.

The resolver requires the exact four named outcomes and obtains the native
constant by name. It never assumes ordinal zero, an obfuscated field name, a
null result, or an arbitrary enum value. The fixture reorders the enum to prove
that ordinal selection cannot accidentally pass.

## Scope of the implementation

`StatusHookContract` accepts a unique concrete instance method with exactly
`(StatusKey, StatusKey, boolean)` parameters and the verified result enum. The
key type must have unique String ID and primitive boolean ownership fields.
The hook reads the second key directly through those fields. Nested message-key
heuristics and field iteration order do not decide status identity or ownership.

| Invocation | Bytecode hook behavior |
| --- | --- |
| Enabled, incoming `true`, identified non-self target | Record the target ID and return native successful acknowledgement |
| Local `false` | Preserve the host's normal execution |
| Self-owned target | Preserve the host's normal execution |
| Missing key, ownership contract, ID, or direction | Preserve the host's normal execution |
| Disabled option | Preserve the host's normal execution |
| Multiple valid manager/key/mapper candidates | Leave the ambiguous hook unresolved |
| Unknown result enum or changed parameter shape | Leave the revoke hook unresolved |

Discovery caches use new namespaces, and cached methods are revalidated before
installation. Playback mapping accepts a unique non-synthetic, non-bridge
instance method with one concrete reference parameter and a compatible message
return type. Existing message-revoke handling, SQLite fallbacks, preferences,
licensing and media retention are outside this patch. Letting the bytecode
method continue does not establish that separately installed SQLite hooks will
allow the same local deletion; that remains part of device acceptance.

## Local validation

Run with JDK 17:

```sh
python3 qa/test_status_hook_contract.py
python3 qa/test_private_hook_logs.py
python3 qa/test_preserved_own_revoke.py
python3 qa/test_hook_return_types.py
```

The new required source-QA suite performs:

- 53 compiled checks of the production reflection/argument/result policy,
  including ambiguous fields, overloads, cached-shape eligibility, genuine
  compiler-generated bridge methods and reordered enum constants.
- 31 checks compiling the verbatim production initialization and status-hook
  methods against explicit DexKit, Xposed, persistence, key-extraction and UI
  doubles. They exercise target persistence, a real enum dereference and distinct
  caller result branches, local/self/disabled fallthrough, ambiguous discovery,
  and validation of cached methods.
- Five source guards for cache changes and removal of the generic first-key and
  generic-result callsites from the status handler.

Using the same harness with the exact baseline source compiled successfully and
failed separately for target identity, null acknowledgement, local/self
fallthrough, ambiguous manager selection and synthetic mapper selection.
Six compiled negative mutations were also rejected: first-key selection,
ignoring the incoming flag, ignoring target ownership, acknowledging no-store,
accepting synthetic mappers, and restoring the null-result callsite. The latter
reproduced the downstream enum dereference failure.

The existing private-log guards, preserved-own-revoke policy and return-type
guards pass. Java syntax parsing of the privacy source directory passes (26 Java
files; Kotlin was explicitly skipped for this Java-only patch). These checks do
not constitute a complete Android build, live DexKit scan, ART/Xposed callback
test, rendering test or end-to-end WhatsApp transport test.

## Required device acceptance

Use authorized test accounts and record the exact host version plus signed
module APK hash. Run the checks on both the intended debug and release artifacts.

1. Receive and open a status, then revoke it from its sender. Check that the
   story remains available, its own ID receives the deleted marker, and a
   distinct revoke-event ID never marks an unrelated story.
2. Exercise repeated revokes and a delayed/orphan revoke. Confirm successful
   incoming processing, no enum-result crash, and no repeating pending event.
   Confirm that ordinary sending and receiving continues afterward.
3. Delete one's own status and perform user-initiated local deletion. Confirm
   that both retain their ordinary host behavior. Repeat with preservation off.
4. Restart the host and reopen the preserved story. Check persistent timestamps,
   playback mapping and rapid transitions between preserved and ordinary stories
   for a stale header marker.
5. Test text, photo and video statuses with locally available media, including
   the relevant Business host separately if it is to be supported. A compatible
   descriptor in one supplied APK does not certify another release or variant.

This patch cannot recreate expired, already removed or never-downloaded media.
Status database fallbacks and asynchronous playback decoration still require
separate acceptance; the change does not certify every Deleted Stories report
or establish the cause of every pending-message report.
