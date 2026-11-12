# Preserved messages: asynchronous acknowledgement acceptance

This document replaces the old synchronous sender acceptance contract for PR #87. Current production already queues manager persistence; success returned from dispatch means enqueue acceptance, not a committed vault row.

## Scope

The complete production sender, provider, SQLite store, lifecycle ownership, cache and policies compile in the standalone runner. Android is Robolectric API 24/28/34. Xposed dispatch, host message identities and unrelated provider services are explicit boundaries, not native injection. Restart/transcription/private licensing services fail if the suite unexpectedly calls them.

## Run

    python3 qa/android_preserved_dispatch_test.py --out /tmp/waex-preserved

Provide --deps, --dexkit, --sdk-jars and --maven for verified cached/offline dependencies as documented by --help. Windows uses the actual Kotlin compiler JVM entry point; the same pinned distribution supplies stdlib. Java 17+ and Kotlin 2.0.20 are required by the tested toolchain. Use --source-root for unchanged production and --expect-assertion-failures only for explicit negative controls.

## Required results

39 methods on each of API 24/28/34: **117 JUnit executions are required**. All must complete. Repetitions are not new coverage. Compilation or bootstrap failures are not successful negative controls.

The existing 28-method matrix covers confirmed/failed inserts, missing and old providers, denied UIDs, SQLite errors, private error text, warning throttling, Delete-for-me continuity and source-message preservation.

Five additional methods establish: the original Delete-for-me completes while the actual provider worker is held by a latch; Throwable logs retain private markers so the oracle can detect leaks; after-callbacks use the invocation snapshot even after self-unhook; after-callback order is reversed; original throwables survive scope cleanup.

Historical PR #87 evidence: official 2.0.6 production completed the former 99-test suite with 39 assertion failures; PR #87 completed it with zero. A deliberate worker log(Throwable) mutation compiled and completed with three privacy failures. These are earlier results, not a run of this expanded suite. The test logger must never sanitize the defect being tested.

Six added methods exercise the actual production callback with nested enabled calls,
an inner disabled option, an unrecognized inner Runnable, the original inner throwable,
another thread, and two callback registrations on one invocation. Before/after callback
extras are per invocation and preserve object identity, as in Xposed's documented
`XCallback.Param.getObjectExtra` / `setObjectExtra` contract. They do not replace the
production ThreadLocal or the feature's actual before/after callbacks.

FIFO barriers are used by tests and teardown only, after the host callback returns. They are not a main-thread production wait or durable delivery guarantee. Unsupported callback-priority/reflection details remain outside this fixture.

## Production guarantee and limits

On the worker, true persistence acknowledgement is accepted; false, null, old empty responses and exceptions use the existing bounded payload-free warning. Local deletion does not wait for manager Binder or vault SQLite. Metadata capture still happens on the original path.

The executor remains unbounded/non-durable. Process termination can lose queued work.
Each Delete-for-me callback now snapshots the previous local scope before checking
preferences or selection, then restores that snapshot after the original invocation.
An inner invocation cannot clear a still-active outer local-delete scope. Each
registration has a distinct key so duplicate callbacks cannot overwrite snapshots
on the same invocation. The outermost callback still removes the ThreadLocal value;
other threads remain isolated. Arguments, results and original throwables are untouched.
Arbitrary cross-profile Binder behavior and actual host selectors are NOT_VERIFIED.
The complete signed APK requires the maintainer's legitimate build path.

## Nested-scope follow-up and history

The focused follow-up starts at PR #87 head
`74b4d1fc472da79a76142341babd768371a8556c` and depends on that existing proposal;
do not open a second acknowledgement PR. Its production delta changes only callback
scope bookkeeping. The resolver, cache keys, message-key extraction, SQL queries,
schema, provider authorization and asynchronous worker remain unchanged.

PR #78 was rejected after its stricter identity lookup stopped captures on a device
(maintainer comment `6260661413`, 2026-10-19). This follow-up does not restore that
resolver, identity lookup, SQL or schema change. The surviving nested cleanup defect
is independently exercised using the current registered callback and current message
capture path. The official Xposed callback API documents extras as invocation-local,
including recursive calls:
https://api.xposed.info/reference/de/robv/android/xposed/callbacks/XCallback.Param.html

Use the exact PR #87 source with this expanded suite as the behavioral baseline.
The four nested restoration scenarios should fail on each Android API; the other
35 scenarios retain their original contracts. A separate negative control that
replaces the callback-specific snapshot key with one shared key must fail the
duplicate-registration scenario on each API. Test results must record actual source
hashes and must not be presented as device or AntiRevoke end-to-end acceptance.

Run that isolated negative control with the same verified dependency arguments:

    python3 qa/mutate_preserved_scope.py --out /tmp/waex-preserved-shared-key

It copies public Java/Kotlin sources into a new directory, changes exactly one
scope-key declaration, and invokes the same 117-execution suite. It accepts only
the three duplicate-registration assertion failures after successful compilation;
it never mutates the input checkout. Those three rejected mutant executions are
not additional passing product tests.

## Executed nested-scope comparison (2026-11-12)

All three runs used the same expanded runner and fixture, Windows 11 build 26200,
Temurin JDK 17.0.20.1+1, Kotlin 2.0.20-release-360, DexKit 2.2.0 and Robolectric
4.17 instrumented Android API 24/28/34. Python 3.15.0a5 launched the standalone
runner. Every Java/Kotlin compilation stage completed successfully before JUnit.

| Source | JUnit executions | Assertion failures | Interpretation |
| --- | ---: | ---: | --- |
| Candidate nested-scope callback | 117 | 0 | PASS for the declared framework suite |
| Unchanged PR #87 head `74b4d1fc472da79a76142341babd768371a8556c` | 117 | 12 | FAIL: the four nested restoration cases fail on each API |
| Candidate with one shared callback snapshot key | 117 | 3 | FAIL: duplicate-registration cleanup fails on each API |

The latter two are successful negative-control experiments, not passing product
implementations. The baseline and mutant JUnit processes returned 1; their runners
returned 0 only because the exact expected assertion failures were present. No
compilation failure or incomplete API matrix was accepted as a negative control.

Candidate source identities (SHA-256):

- Hook: `5be75ccbc915b802fe9ee5b20e288cb14b3906c8b697e96119b3d2216157e7b8`
- Runner: `0e1068268eac552c7ca68dea08cf7d91820c9303fe5d8a740d3787f45bfd5162`
- Fixture: `faf028650d5bceef57a7f69634a194e59fdf860a397449d181e46577e86fbb95`
- Mutated hook: `3f04eab1055ed267d62758d406078adb6968267b3ac9c5453a5e38ea3aeec1ee`

The baseline Windows checkout was clean at the stated Git revision. Its CRLF hook
hash was `566bf976e1f3625f0371ba95d90e8766df32ba037be550d1b2303cc583f3565b`;
the same Git blob checked out with LF hashes to
`88525b89fcf288aa8fafc93e26ce24bf40aec6815bcb015119e8aaf6f67277a2`.
The candidate files were transferred byte-for-byte, with matching local and lab
hashes. The result manifests record every compiled production source hash.

Saved result-manifest identities (SHA-256):

- `candidate_01/result.json`: `9daa8a5c1edd3a4d66f19153c9dc95d1b44f7137ef55982b24069727e3b1a99f`
- `base87_01/result.json`: `d613d9bd8f5873abfed94c4e1c9dad2f56dfb23df4e99b8338fb8f4072afceff`
- `shared_key_01/run/result.json`: `247312dd494838fd2089a5f7a87e59dc9466f372556d6366c99da104d791c70f`
- `shared_key_01/result.json`: `6aeed48548edb67da4367919525015af21693c82ba1562579c84cabe5f27d0ee`

The own-revoke Java contract and exception-message privacy guard also passed with
the same Windows JDK. Python syntax checks and `git diff --check` passed locally.
These results do not establish native hook resolution, AntiRevoke end-to-end
behavior, durable delivery, real WhatsApp preservation, APK build success, device
compatibility or performance improvements. Those acceptance boundaries remain
unchanged.

## Device acceptance

Use authorized test accounts and signed contributor builds. Verify local deletion with a blocked/unavailable manager, successful vault storage, denied inserts, bounded sanitized logs, reboots, managed profiles and Debug/Release separately. Never count an enqueued operation, ACTIVE label or a passing JVM fixture as a confirmed real-device saved message.

PR #87 must retain its existing history and storage guarantees when reconciled with main; do not force-push or restore the former synchronous sender.
