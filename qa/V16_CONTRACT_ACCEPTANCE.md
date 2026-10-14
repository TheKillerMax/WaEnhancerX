# V16 receipt execution and incoming presence contract review

Experimental fork integration; not an APK release or a completed Android/LSPosed test.
Base upstream main: `4bbe5cb02ce2fe924136a9579d2582c1a4818643`.
Prior integration: `3e905763cff99331d5cce5857e5889716d4947ad`.

## Receipt execution

The previous hook cancelled every declared non-static SendReadReceiptJob method,
including retry, initialization, diagnostics and deserialization. The revised
class-scoped DEX matcher requires exactly one zero-argument void method using
both exact `receipt` and `status` literals. Runtime shape and callback identity
are checked again. No obfuscated method name is pinned. Constructor capture,
status preferences and exact-recipient/Ghost Mode policies remain unchanged.
A missing/ambiguous execution match logs incomplete job-level privacy coverage;
existing other receipt guards remain, but unsupported-host privacy is not certified.

## Incoming presence

The previous available anchor matched a multiplexed Runnable in the supplied
WhatsApp 2.26.39.79. Scanning its receiver graph or toString for a JID is not
presence evidence. The new matcher selects a unique Handler.handleMessage(Message)
using the connection-ready, lastSeen and presence literals. Only successful host
callbacks are observed, never cancelled or modified. The reviewed envelope is
what=5, arg1=5 (available) or arg1=64 (unavailable), with a BaseBundle payload and
an explicit string jid in the supported contact namespaces. Unknown codes,
unrelated addresses, non-string values and denied/unknown presence are ignored.
Unknown/denied events do not clear previously cached state: cache freshness and
last-seen precision still need separate review. Other notification routes are unchanged.

## Evidence and limits

The supplied host SHA-256 is
`9c5d5cb8f39d0b283d439f0126b5637094e85a47407ee3e88640f9df2a543440`.
It has an Android Debug signer, not verified official-distribution provenance.
The observed literals and event codes are not a universal protocol guarantee.

New source/JVM regressions compile the actual production installers/decoders
and policy classes using explicit Android/Xposed/DexKit doubles. Receipt tests
cover 45 checks; presence tests cover 104 checks including 2,000 seeded unknown
code probes. Twenty-five deliberately unsafe variants failed behavioral assertions.
Local integrated validation passed 41 test scripts (one requires the local APK)
and separate production syntax parsing of 79 Java and 105 Kotlin files.
Both query builders also compiled and instantiated against declared DexKit 2.2.0:
https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38648430467
This is not native DexKit execution, ART verification or a full Android build.

Run `python3 qa/test_receipt_job_execution_contract.py` and
`python3 qa/test_presence_event_contract.py`; retain the existing integrated suites.
Use two authorized test accounts for normal sending, status-view privacy, process
restarts, offline/online transitions, receipt retries and concurrent notifications.
The cause of issue #38 and the reported online/delete-toast substitution are not
established or claimed fixed. No licensing, signing, APK or private data is changed.
