# WaEnhancerX — integration preview (13 open PRs plus fork safety changes; Android unverified)

This **experimental fork branch** stages the current public source-level changes of PRs
[#12](https://github.com/WaEnhancerX/WaEnhancerX/pull/12),
[#13](https://github.com/WaEnhancerX/WaEnhancerX/pull/13),
[#15](https://github.com/WaEnhancerX/WaEnhancerX/pull/15),
[#17](https://github.com/WaEnhancerX/WaEnhancerX/pull/17),
[#23](https://github.com/WaEnhancerX/WaEnhancerX/pull/23),
[#25](https://github.com/WaEnhancerX/WaEnhancerX/pull/25),
[#26](https://github.com/WaEnhancerX/WaEnhancerX/pull/26),
[#27](https://github.com/WaEnhancerX/WaEnhancerX/pull/27),
[#32](https://github.com/WaEnhancerX/WaEnhancerX/pull/32),
[#33](https://github.com/WaEnhancerX/WaEnhancerX/pull/33),
[#34](https://github.com/WaEnhancerX/WaEnhancerX/pull/34),
[#35](https://github.com/WaEnhancerX/WaEnhancerX/pull/35), and
[#36](https://github.com/WaEnhancerX/WaEnhancerX/pull/36).

**Do not release, install over a personal WhatsApp database, or merge this snapshot as-is.**
It is a source-composition candidate, **not** a record of 13 Git merge operations.
Upstream `main` was not modified. Individual upstream PRs remain open.

## Provenance

- Upstream `main` at composition time: `6a34158ff8f1dcad346e34fec6db67dc79cc1e8f`
- #17: `48893573cc009bd6398fe0d7d3ce126e450d62b9`
- #25: `32aa6b25d7875ff9444f5d3d40244f9d0b2753d6`
- #26: `bb125d4a85d0aa4a6d398632fa8746eb69e8776d`
- #27: `e53f7b92f033a61b1a25a084c5651ff5b0bf3188`
- #32: `4cbfb68227eef4ecdc0001911cb8f2f2722dda7f`
- #33: `a3a8b978fa8123032959560abeb5e472a6cca7d5`
- #35: `b9a191839124569dc7135fc4f5c1873a4dcd6b4f`
- #34: `4aa0bf9fb0ca8431da546e5e04bfb8f7c8f07c9a`
- #36: `ec5e34cd3c50aa220b7de862f0d072a2a4c3bf6b`
- Other branch HEADs are recorded in their corresponding linked PRs.

Files unique to a PR use the exact Git blob object from that branch. Shared
`AntiRevokeHook.java` and `AntiEditMessagesHook.kt` select #17, where #25's
sensitive-log redactions were previously incorporated. Shared
`BlueOnReplyHook.java` selects #35, which retains those redactions and
replaces the JID-wide bypass. Shared `FeatureCatalog.kt` and
`StylesSettingsScreen.kt` were composed from the #35 version with #34/#36
patches applied, preserving the proximity, manual blue-tick, and archived
chat settings.

The #25 log QA test was updated to recognize both standalone legacy code and
the hardened #35 implementation, plus the #17 asynchronous edit writer.

## Additional fork-only hardening (not part of the 13 upstream PRs)

- `fix/styles-canonical-boolean-aliases-2026-10`, HEAD
  `6bb6134bde372840fa6c41a8f007b50b2548fa44`: four existing Boolean
  display-key aliases now write canonical preference keys. The screen uses
  `putBooleans()` and only reflects committed settings; Audio-to-Voice paired
  flags are written atomically. A separate policy disables five incorrectly
  Boolean-rendered STRING/STRING_SET settings with visible "Needs typed editor"
  feedback until semantic editors are built. The #34 proximity and #35 manual
  `seentick` behavior is retained.
- `fix/privacy-redact-exception-text-2026-10`, HEAD
  `1c4cfb172b4d75d653fb06ec093d157b890541fe`: error logs in
  `CustomPrivacyHook`, `MediaPreviewHook` and `PreferenceBridgeClient`
  emit exception class names rather than raw messages; the bridge runtime
  status no longer stores exception text. This is a targeted redaction, **not**
  proof that all module logging has been audited.
- `fix/privacy-call-log-diagnostics-2026-10`, HEAD
  `d56e1064e578d9250c617984852fdc4e8f2d6622`: 9 error reports
  in `CallPrivacyHook.java` now record only the exception class, not
  unbounded text that might include call JIDs or phone information.
- PR #32 now keeps **all schema-known keys** untouched in old JSON backups,
  prevents an old alias from overriding a present canonical key, and removes
  two unrelated privacy migrations (`typing_online_toasts` to
  `typing_privacy`, `hide_seen_receipts` to `hidereceipt`).
  Executable Kotlin fixtures check both JSON orders, independent privacy
  values and preservation of 293 exported binary settings. The fixture
  uses a limited `JSONObject` substitute; it is not a parser conformance test.
- These fork branches are **not automatically upstream PRs**. GitHub denied
  creating the Styles upstream draft via integration permissions (HTTP 403);
  the fork branches remain available for maintainer review.

## PR #25 and #27 consolidation

The three former fork-only logging fixes are now **part of PR #25**
(commit `32aa6b25d7875ff9444f5d3d40244f9d0b2753d6`), including ten source-matched files and their independent
regressions. `qa/test_private_hook_logs.py` runs all three supplemental checks.
See [the expanded review scope](PR25_EXTENDED_SCOPE.md). These changes were
committed to #25's existing branch, **not merged into upstream main**.

PR #27's source workflow now lists the added regression scripts separately,
when present, and remains safe to merge before #25. At this point, the
combined test runner still needs to be run on the updated preview head.

## QA evidence and limitations

- The isolated, source-matched JVM receipt suites passed **945,342**
  assertions, including **100,020** checks verifying that a read-receipt
  allowance cannot override delivery hiding or Ghost Mode.
- All six application orders of the three FeatureCatalog patches and both
  StylesSettingsScreen orders were checked for exact context compatibility
  and key wiring. This does **not** prove Kotlin/Android compilation.
- The source-level logging expression detector identified no unsafe
  expressions across 58 tested logging callsites in six files.
- Git tree comparison was used to verify the source composition against the
  contributor PR branches. Prefer re-running all checks on this exact branch
  before treating any result as integrated validation.
- No Android Gradle build or live LSPosed / WhatsApp end-to-end test has
  succeeded in this environment. The Android SDK, Gradle distribution access,
  and authorized private `:licensing` module remain required.
- The supplied WhatsApp APK has an Android Debug signing certificate and is
  **not** proof of official production-app compatibility.
- Latest V10 green checks:
  [#38484594137](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38484594137)
  for Kotlin backup identity/JSON precedence and
  [#38484907583](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38484907583)
  for the same plus 9 call privacy diagnostics. Both are source/JVM
  regressions, **not** Android builds.
- **Real GitHub Actions source/JVM CI succeeded**, including
  [#38478229881](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38478229881),
  [#38478806496](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38478806496),
  [#38480211486](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38480211486),
  [#38480775579](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38480775579),
  [#38481194953](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38481194953)
  and [#38481843223](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38481843223).
  The last link validates the privacy redaction source checks at
  `554a1a2f24b241e9feda27cf695a0ac845f9de2c`. This covers source
  parsing/JVM contracts only; Gradle APK and LSPosed/device checks remain
  entirely unverified.

## V11 verification — bounded imports, failure compensation and safer logs

- **Backup restore failure compensation**, PR #32 at
  `4cbfb68227eef4ecdc0001911cb8f2f2722dda7f`: before touching
  `private_config` or `waex_prefs`, the codec snapshots the touched
  preference keys and their original runtime types. If either store commit
  fails, it attempts restoration in both files and clearly reports when the
  compensation itself is incomplete. **This is best effort, NOT a true
  atomic multi-file transaction**; simultaneous writers and persistent disk
  errors remain device-level risks.
- The same PR now **reads imported settings with an active 8 MiB cap**,
  reading no further than the first overflow byte. A synthetic >9 MiB
  stream, exactly-limit invalid data, zero-progress reads and stream-closing
  behavior are covered by executable Kotlin fixtures.
- Fork branch `fix/privacy-redact-db-dialog-status-logs-2026-10`,
  `29ce617c43b217536596b4680ba5470301567eab`: 18 exception
  log callsites in `MessageStore.kt`, `NativeWhatsAppDialog.kt`, and
  `StatusDownloadHook.java` now log only exception classes.
  User-facing status download error toasts were retained.
- **Actual green GitHub Actions runs**:
  [#38487490242](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38487490242)
  (rollback failure injection),
  [#38487898243](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38487898243)
  (18 log callsites), and
  [#38488123042](https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38488123042)
  (streaming import cap). The latest workflow confirms **105 Java + 104
  Kotlin syntax parses**, 293 exportable preference round-trips, and all
  selected JVM/source regressions. It does **not** build a new APK.

## Recommended checks on an authorized development system

Run the read-only/source-level QA scripts, especially:

```sh
python3 qa/test_private_hook_logs.py
python3 qa/test_blue_receipt_recipient_isolation.py
python3 qa/test_manual_blue_tick_ui.py
python3 qa/test_notification_memory.py
python3 qa/test_proximity_ui_wiring.py
python3 qa/test_archived_chats_entry.py
python3 qa/test_deleted_indicator_preference_types.py
python3 qa/test_feature_preference_schema_coverage.py
python3 qa/test_settings_backup_binary_roundtrip.py
python3 qa/test_syntax_checker.py
python3 qa/test_style_boolean_alias_wiring.py
python3 qa/test_style_non_boolean_guard.py
python3 qa/test_exception_message_privacy.py
python3 qa/test_call_privacy_logs.py
python3 qa/test_database_dialog_status_log_privacy.py
python3 qa/test_backup_alias_policy.py
python3 qa/test_settings_backup_binary_roundtrip.py
```

Then, with an authorized Android toolchain, run `assembleDebug` and
`assembleRelease`. Use an isolated test device and authorized WhatsApp build
to validate receipt types, Ghost Mode, LID/group routing, status decorations,
manual chat identification, preference round-trips, and upgrade migrations.

No claim is made that all 93 catalog entries are runtime-functional.
