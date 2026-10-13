# WaEnhancerX — integration preview (13 open PRs, unverified)

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
- #25: `d238a0f3b027403cdca69287f609c5bdc530049e`
- #26: `bb125d4a85d0aa4a6d398632fa8746eb69e8776d`
- #27: `b559b9c3bc825681c3992b54d88eacf8fa20ba06`
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
- Zero GitHub Actions workflow executions or status checks were observed for
  the preview commits at the time of preparation.

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
```

Then, with an authorized Android toolchain, run `assembleDebug` and
`assembleRelease`. Use an isolated test device and authorized WhatsApp build
to validate receipt types, Ghost Mode, LID/group routing, status decorations,
manual chat identification, preference round-trips, and upgrade migrations.

No claim is made that all 93 catalog entries are runtime-functional.
