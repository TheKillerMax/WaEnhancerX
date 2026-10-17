# Forwarded metadata: narrow mitigation and acceptance

Based on reviewed upstream 025ff5494df4c9f4a94a7cada787c299f68a95d2. Run `python3 qa/test_forwarded_metadata_scope.py`.

The old FMessage_setForwardScore lookup resolved a numeric flags OR setter in the supplied 2.26.40.76 host. That interception is removed rather than replaced by a guessed obfuscated method. Existing positive INT forward_score entries in the exact message_forwarded table are the only remaining modified values; forward_origin and transport flags are left intact. Explicit canonical false is respected over a true historical hidetag alias. Corrupt settings do not grant implicit permission.

This store-only behavior is narrower than the old implementation. It does not guarantee removal of labels already rendered or computed from in-memory metadata. It does not identify the full forwarding protocol or prove the cause of the Meta AI delivery report. The remaining forwarding-score database operation requires host-level acceptance. No message payload, cryptographic key, license or transport job is changed by this patch.

The whole Kotlin hook compiles with explicit Android/Xposed adapters and its registered callbacks are executed. Real SQLite insertion, native DexKit, WhatsApp delivery and LSPosed are not exercised. Using consenting accounts, compare normal messages, private/group forwards, Meta AI forwards, canonical/legacy settings, malformed stored types and concurrent sends; confirm reception from another account, not only the local tick. Verify flags and origin metadata are preserved before accepting the change. Do not reset all user settings as a substitute for this test.
