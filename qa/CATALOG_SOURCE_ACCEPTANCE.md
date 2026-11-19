# Reviewed catalog source QA — 2026-11-19

## Reproduced problem

On upstream `nightly@eee15668e7dab08b4cfff90b6be441e91d73021b` (and the
blob-identical catalog inputs on `main@39bb7ad57dbfcb324f713ce46d681720946150b9`),
`test_catalog_source.py` fails two assertions before this change:

- Its historical 92-key expectation disagrees with the 97-key canonical catalog.
- Its two-resource Meta AI expectation rejects the three newer, actual
  sub-control resource names.

`test_catalog_schema_alias_contract.py` independently stops at its historical
93-key count. The inventory extractor itself passes and reports 97 canonical
entries. These are stale **QA expectations**, not evidence that the five net
added features are broken or that their hooks work.

## Reviewed production history (not a generated expectation)

| Change | Source-history evidence | Current contract |
| --- | --- | --- |
| Parallel download | `d07cbd01`; schema/backup follow-up `bc8af5fd` | Boolean `parallel_downloading`, media utility route |
| Device emoji | `7bcf74ef` | Boolean `disable_defemojis`, conversation controls |
| Custom emoji | `bb70f71c` | Boolean `custom_emojis`, conversation controls |
| Floating navigation | `45fbed77` | Boolean `native_floating_navigation`, visual appearance route |
| Sticker outline | `7c06db57` | Boolean `remove_sticker_white_outline`, conversation controls |
| Locked-chat notification | `8521582c` | Boolean `locked_chats_message_notifications`, privacy/security vault |
| Removed old anti-revoke entry | `75c3b48b` | `hide_anti_revoke` is no longer a canonical catalog key |
| Meta AI sub-controls | `74967207`, later localization `88a5186b` | Home FAB, entry-points and block-chat controls have explicit UI resource, preference, schema and hook reads |

The six additions minus one removed key explain 92 -> 97. The later 93-key
assertion already included the device-emoji/parallel-download/removal state;
four later additions explain 93 -> 97. The historical tests remain recoverable
through Git rather than having their meaning silently relabelled.

## Verification design

`catalog_expectations.py` contains an independent, explicitly reviewed set of all
97 canonical keys. It never loads the production catalog to manufacture an
expected set. The source and schema tests share this reviewed contract rather
than drifting between separate size counters. Unknown additions, missing keys,
duplicates and same-size substitutions still require explicit review and fail.

The six newly reviewed routes also pin group, tab index, subtab, tab id and Pro
flag. All six must remain typed Boolean schema entries. Existing checks for
legacy backup aliases, navigation-only entries, canonical routes, non-empty
labels and excluded non-catalog preferences stay in place.

Meta AI validation still requires the two Spanish resource sets to match and
exactly five non-empty resources. Each sub-control has an independently reviewed
resource, preference key, state variable and semantic hook-reader association.
Complete tokenized source fragments pin its initial getter and default, displayed
state, callback setter, successful-write guard, state update and named hook
reader. All three complete controls must belong to the enabled `metaai` parent.
Typed public-schema checks remain. The default flags and existing parent
`metaai` preference were not changed.

New negative controls reject:

1. A missing `custom_emojis` catalog entry.
2. A same-size replacement with the schema-valid but non-catalog
   `parallel_downloading_connections` key.
3. A changed destination for `locked_chats_message_notifications`.

The schema/alias script also exercises the first two negative cases alongside
its existing unknown-entry, bad-alias, privileged-navigation and missing-schema
controls. No failure is suppressed, no threshold is widened, and no production
or workflow file is changed.

## Commands and results

Run from the checked-out repository root with Python 3.10+:

```sh
python3 qa/test_catalog_source.py
python3 qa/test_catalog_schema_alias_contract.py
python3 qa/test_feature_contract_inventory.py
git diff --check
```

In the Linux scratch environment with Python 3.12.14, the first candidate
`fa5d1b90b2a2195efef2b8d29d830806d39e3dba` passed all 22 unittest methods in
`test_catalog_source.py`; the schema script passed with
97 catalog entries, 390 typed preferences, 10 active legacy aliases and three
navigation-only routes; the inventory script passed. The original baseline
failed the three stale assertions described above. Negative fixtures are part
of these test executions, not an additional count of proven product features.

## Follow-up: reject swapped Meta AI bindings

Independent review demonstrated that the first candidate's global string
presence assertions still passed after exchanging only the home-FAB and
block-chat setter keys in memory. Both keys remained present, so those checks
did not establish which UI control owned each key. This is a **QA false negative**,
not an observed production wiring defect. The first commit and its original
comparison results are retained; the correction is a new commit.

The follow-up replaces the loose UI/hook presence checks with the complete
source-fragment associations described above. Whitespace and comments do not
affect matching, while string-literal contents remain significant. Unrecognized
code shapes and nested block comments fail closed and require explicit review;
this intentionally bounded checker is not a Kotlin or Java compiler.

Two new unittest methods use the actual source read into memory. Six subtests
exchange the setter keys, initial getters, checked-state variables, post-write
state assignments, title resources and semantic hook-reader keys. Two further
subtests remove dependence on the write result or change the initial default.
Every mutation must be rejected, and source files are never rewritten. Existing
catalog snapshots and all previous negative controls remain intact.

The follow-up passes 24 unittest methods, the schema/alias script and the feature
inventory script. A separate comparison runs the **same original positive test
method** under a read interception containing only the two swapped setters:
the first candidate incorrectly accepts it, while the follow-up rejects it with
the specific home-FAB control-binding assertion. These are eight in-memory
negative fixtures plus one differential re-execution of the setter fixture, not
nine independent product behaviors. The original nightly baseline still fails
its historical stale expectations, as recorded above.

Hosted CI has not executed this candidate. The current nightly gate's draft
policy, upstream workflow approval requirements and other open PR test failures
are separate concerns; this change does not bypass those controls.

## Limits and recovery

This is source metadata QA. It does not prove preference IPC, UI rendering,
persisted user changes, host hook resolution/execution, supported WhatsApp
versions, work-profile behavior or complete signed APK functionality. No Android
device, app data, entitlement or signing key was modified. Roll back by reverting
this QA-only commit; no data recovery or migration is required.
