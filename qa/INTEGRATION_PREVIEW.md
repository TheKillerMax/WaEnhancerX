# Current-main integration preview — 14 October 2026

**Experimental fork branch, not an upstream merge or a release.**

Base: `WaEnhancerX/WaEnhancerX:main` at `4bbe5cb02ce2fe924136a9579d2582c1a4818643`.
The supplied source ZIP reproduced its full Git tree, `cf645c191c4ef360688b06606ea87dda5a561265`.

## Current composition

This branch contains real Git merges composing PRs #26, #27, #12, #13, #32, #15, #17, #25, #35, #36 and #23, plus the checked typed-save correction now submitted as PR #39. Already merged upstream PRs #33, #34 and #37 and the newer typed Styles editors are retained.

| Contribution | Verified source head |
| --- | --- |
| PR #15: lifecycle reconciliation | `a82d62fff75135f5ac2bc73971617c567edfa1aa` |
| PR #35: exact receipt routing and current Styles | `3f7136929a4e5ec8f7d12c38a477e3c3bd38e852` |
| PR #39: checked typed Styles saves | `dbc1312e5b827acdaaedf58c3961c73400225592` |
| PR #32: canonical backups and validated JSON import | `ed4427a88ed6a4fb8ee63d949f2c21880ab37dc2` |
| PR #27: source CI including pinned Android JSON tests | `6440a940de68319cf72b0c5ee7c0aeccac482928` |

Before this documentation commit, the integrated head was `782cf55c28ee1e14cda925d749ccd4203555a616`, tree `7dd6da80733e0cf64cc8e0094cf3f369c554e0a3`. PR #32 and the preview were published in one atomic non-forced push only after all validation steps passed. No upstream main ref, release or issue state was changed.

The previous preview on `6a34158...` and the prior integration head `9cb058eeae91729801d334a71857800033efa0f5` are historical, not the latest reviewed source.

## Preserved functionality

- Startup keeps the first-visible-Activity injection toast, one-time listener cleanup, runtime-health reporting and current hook registry while isolating initialization failures.
- Receipts keep exact-recipient/message-ID allowances, delivery/Ghost Mode precedence, bounded state and PR #25 diagnostic redaction.
- Styles keeps proximity, string-valued `seentick`, canonical Boolean batching, Pro gates and the five current typed editors. Their checked writes report failure rather than unconditionally closing the editor.
- Existing backup canonical-key precedence, blocked/secret exclusions, historical alias contracts, storage routing and compensating restoration remain in place.

## Backup defects reproduced with actual Android JSON

The existing integration passed all 38 previous standalone suites. Replacing synthetic JSON behavior with unmodified, hash-pinned AOSP Android 14 `org.json` exposed additional failures. The old codec passed only 35 of 105 new named scenarios; 70 failed. These are scenario failures, not 70 distinct bugs or affected users.

The revised codec:

- Rejects invalid Boolean inputs instead of silently converting them to false.
- Preserves legitimate true/false and 0/1 representations without stringifying JSON null or containers.
- Validates integral values and ranges without truncation, wrapping or routing quoted Long values through Double; rejects non-finite Float values.
- Supports actual JSON arrays for versioned string sets and rejects invalid mixed elements rather than partially converting them.
- Validates supported JSON schema version 1 and rejects trailing content, raw NUL, malformed UTF-8, excessive record/set counts and nesting beyond 64 levels.
- Rejects duplicate binary record keys, invalid Boolean bytes and binary trailing content.
- Checks serialized export size before emitting a header, enforcing the same 8 MiB container limit used by import.

Valid legacy aliases and current binary/versioned-JSON key precedence are retained. Invalid individual values are skipped without overwriting their existing settings; a mixed input can still restore other valid entries. This is not a new all-or-nothing transaction across two preference stores.

## Executed evidence

Current validation/publication run: https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38641507327 — **success**.

- 45 successful remote processes: five standalone backup/schema suites, standalone production parsing, integrated production parsing and all 38 APK-independent integration suites.
- Integrated production parsing: 77 Java and 105 Kotlin files. Standalone PR #32 production parsing: 56 Java and 102 Kotlin files.
- 39/39 local integration suites passed, including the host-class relocation test against the locally supplied WhatsApp APK. The APK was not uploaded to Actions.
- New Android JSON regression: 105/105 named scenarios, including 2,000 seeded integer cases, exact 8 MiB and 10,000-set-entry boundaries, and 293 preferences preserved by name/type/value through actual versioned JSON.
- Existing binary round-trip and compensating-restore regressions remain passing, including all 293 exportable preferences.
- Fifteen deliberately unsafe codec variants were rejected by behavioral test failures, not compiler failures.
- Four infrastructure negative controls rejected missing source, altered AOSP source, missing compilers and a missing codec with exit code 2.

`qa/test_settings_backup_json.py` compiles six unmodified Android 14 JSON sources pinned by SHA-256. Context, SharedPreferences and annotation types are doubles. These are **host JVM tests, not Android device or filesystem tests**. The runner fails closed on unavailable tooling or source-integrity failures; verified sources can be supplied offline with `--json-source-dir` or `WAEX_AOSP_JSON_SOURCE_DIR`.

Historical source validations remain available at runs 38635239301 and 38635607012. They predate the new parser hardening.

## APK signature checks performed locally

SDK Build Tools 36.0.0 `apksigner verify --verbose --print-certs` accepted the supplied WAEX 2.0.2 Debug, WAEX 2.0.2 Release and WhatsApp 2.26.39.79 APKs with v2/v3 verification. Controlled one-byte alterations of copies of all three were rejected with content-digest mismatches; originals were unchanged.

The WAEX signer SHA-256 is `284325b6f0ca18da5e4c237a6c0618c2a22b08ff8d4a5d11fd12478dad690a84`.
The supplied WhatsApp signer SHA-256 is `44c3bb8c7ea35b3bb11cbfa3c2f5879240df2e49e39816b4437b9856fbb29541`, with Android Debug identity. Signature integrity does **not** establish official WhatsApp provenance, successful installation or runtime compatibility.

## Outstanding acceptance gates

No full Gradle Android build, APK installation, Binder device test, live receipt delivery, memory profile, Android database upgrade or LSPosed execution was performed in this continuation. Authorized private licensing dependencies and matching signing material remain unavailable, and the authorized remote test device was offline.

A failed SharedPreferences commit is not a rollback guarantee; memory can change before disk persistence fails. The separate manual `seentick` void-setter path is still not hardened by PR #39. JSON duplicate-property handling remains AOSP behavior, and an empty exported container retains its historical behavior. This is not a strict RFC JSON validator or a claim that every historical backup is accepted.

The inventory still lists 93 catalog entries, not 93 runtime-certified features. Existing literal-anchor findings (45 present out of 56, 11 absent) are static evidence from the prior source/host comparison, not newly repaired method contracts. Native 16 KiB compatibility still requires separate validation.

Issue #38 lacks an exact full host version and diagnostic trace. Its sending failure is not diagnosed or claimed fixed. Injection, memory, receipts, proximity, archive, status and media issues remain subject to real-device acceptance. The inherited extra EOF blank line in PR #25's logging test is not corrected by this backup-only change.
