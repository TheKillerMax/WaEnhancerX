# Current-main integration preview — 14 October 2026

**Experimental fork branch, not an upstream merge or a release.**

Base: `WaEnhancerX/WaEnhancerX:main` at `4bbe5cb02ce2fe924136a9579d2582c1a4818643`.
The source ZIP supplied for this review reproduced its full Git tree, `cf645c191c4ef360688b06606ea87dda5a561265`.

The previous preview based on `6a34158...` is historical. Upstream has already merged PRs #33, #34 and #37 and added five typed Styles editors plus their current consumers. This branch preserves those changes rather than restoring the older disabled controls.

## Composition and provenance

Real two-parent Git merge commits in this fork compose PRs #26, #27, #12, #13, #32, #15, #17, #25, #35, #36 and #23, followed by a separate checked typed-save fix.

Before this documentation commit, the integrated head was `c23fdb119c2fa602e8776a52a8720a0159f6b851`, with full tree `0e32a7b38d7251728a547157a596000ba16afb26`. That tree is exactly equal to the locally reviewed and tested source composition.

Updated independent contributions:

| Contribution | Verified source head |
| --- | --- |
| PR #15: lifecycle reconciliation | `a82d62fff75135f5ac2bc73971617c567edfa1aa` |
| PR #35: exact receipt routing and current Styles reconciliation | `3f7136929a4e5ec8f7d12c38a477e3c3bd38e852` |
| PR #27: typed Styles and catalog CI coverage | `3d10f12c958cc01c9bbf055860e33cb2ebfb684a` |
| `fix/styles-typed-save-failure-2026-10-14` | `dbc1312e5b827acdaaedf58c3961c73400225592` |

The PR #15 and #35 refs were advanced without rewriting their history. Four fork refs were published in one atomic, non-forced push after validating pinned heads, exact trees and tests. No upstream main ref, release or issue state was changed.

## Reconciliations

- Startup retains the upstream first-visible-Activity injection toast, one-time listener cleanup, runtime-health reporting and the newer Styles hook registry while keeping initialization failure isolation.
- Receipts retain exact-recipient and message-ID allowances, delivery/Ghost Mode suppression precedence, bounded state and sanitized diagnostics.
- The shared BlueOnReply source preserves PR #35 behavior together with PR #25 log hardening; the resulting file matches the independently reconciled receipt branch byte for byte.
- Styles retains the current proximity preference, manual string-valued `seentick` control, canonical Boolean switches, Pro gates and five typed editors.

## New typed-save correction

The five editors previously called void preference setters and unconditionally closed, even when persistence failed. The checked public STRING/STRING_SET writers now return the actual commit outcome, validate schema/store/type, copy set inputs and notify only after success. The editor stays open with its input and an error toast after a failed save.

Current destinations are `css_theme`, `change_dpi`, `chatfilter`, `waex_menu_style` and `hidetabs`. Historical backup aliases such as `custom_css` and `show_home_menu` remain separate contracts and were not silently remapped.

This does not guarantee rollback after a failed SharedPreferences commit: Android may update memory before disk persistence fails. Tests explicitly model that distinction. Other void setters, including the existing manual `seentick` persistence path, are outside this correction's scope.

## Executed evidence

- Source capture and independent merge-tree diagnostics: https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38631486015 — success.
- Exact-tree reconstruction, source/JVM validation and guarded fork publication: https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38635239301 — success.
- The publication job executed 54 successful test/check processes: 13 standalone typed-branch suites, one startup check, two receipt suites, one syntax pass and 37 integrated suites. These are repeated executions across candidates, not 54 independent runtime features.
- Remote parsing covered 110 Java and 107 Kotlin files, including QA fixtures. Local production-only parsing covered 77 Java and 105 Kotlin files.
- Local integration additionally ran the host-class relocation test against the supplied WhatsApp APK: 38/38 local suites passed. The proprietary APK was not uploaded to GitHub Actions.
- Typed-save regression: 87 production manager checks using Android doubles, five editor/consumer contracts and 14 unsafe source fixtures rejected. The existing 100,023-check non-Boolean policy suite remains intact.
- A pre-existing extra EOF blank line in PR #25's `qa/test_private_hook_logs.py` remains an inherited formatting warning, not a claim that the full integrated diff is whitespace-clean.

## Outstanding acceptance gates

No Gradle Android APK build, installation, Android Binder test, populated-device database migration, live receipt delivery, memory profile or LSPosed test was performed. The authorized private `:licensing` module, matching signing material and a test device are not available to this review environment.

The source inventory still has 93 catalog entries; this is not 93 verified working features. Source-derived DEX checks against the supplied host found 45 of 56 literal anchors, with 11 absent. Presence does not prove method semantics; absence only rules out the corresponding literal lookup. The supplied WhatsApp APK has an Android Debug certificate and is not evidence of official distribution compatibility.

Issue #38 reports blocked outgoing messages but lacks an exact full host version and diagnostic trace. Its cause was not established and it is not claimed fixed. Existing memory, injection, receipt, proximity, archive, status and media issues remain subject to device acceptance.
