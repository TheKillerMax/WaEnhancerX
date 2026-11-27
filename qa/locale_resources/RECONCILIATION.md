# Spanish resource checks on current nightly

The original resource PR #175 added 510 resource entries across five XML files.
All 510 entries are already present with equal XML values and attributes in
nightly c089458569564c241e6e2cddbd5a4de301299f28. They are not added again.

This reconciliation supplies eight missing Bubble Colors strings in each of
es and es-419, preserves the stronger HMA display-boundary source checks, and
runs the independent resource contract checker from the existing localization
QA entrypoint. The reference contains 1834 string/plural rows (including the
two recording plural forms); the repaired Spanish tables each contain 1834.
The checker also verifies 17 negative and 13 positive oracle controls, 127
format templates per locale and 13 runtime-formatted templates marked false.

Run independently from a checkout:
  python qa/test_es419_localization.py
  python qa/locale_resources/check_resources.py --root . --out NEW_EVIDENCE_DIR

The optional historical Android table probe from #175 is not represented here
as newly validated. These source checks do not establish physical rendering,
runtime hook behavior or full APK compilation. The current public CI and
maintainer review remain required for integration.
