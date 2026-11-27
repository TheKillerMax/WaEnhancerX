# Resuming manual-retry mutation checks

This change adds a developer QA resume option, not a WhatsApp receipt feature.
The initial resume-only change was prepared against
`nightly@9972e49fac9bfb650c25ee31fde0da9425b67175`, where the manual-retry and
scoped-string fixtures were retained as they stood. Earlier fixture corrections
from PR #200 were already present through merged PRs #180/#186. The current
reconciliation below adapts the retry harness to the current production API,
preserves all fourteen original scenarios and adds three pre-enqueue veto cases.

The default command still executes every mutation:

```sh
python3 qa/mutate_manual_receipt_retry.py --out /tmp/new-full-matrix --kotlinc /path/to/kotlinc
```

To resume at a named case, use a fresh output directory:

```sh
python3 qa/mutate_manual_receipt_retry.py --start-at lost-delivery-only-retry --out /tmp/new-resumed-matrix --kotlinc /path/to/kotlinc
```

`--start-at` selects that case and every later case in the original order. Unknown
names fail before creating the output directory. The selection regression suite
runs before a valid matrix, and failure or a missing suite is a real failure.
`result.json` retains only cases actually executed; the printed summary declares
`completed_mutations`, `total_mutations`, `start_at` and `full_matrix`. A resumed
suffix does not establish that preceding cases passed. No earlier evidence is
silently reused, and an existing output directory is never overwritten.

Each selected mutant must compile, complete the seventeen-scenario behavioral
matrix (the original fourteen plus three current pre-enqueue privacy veto cases), exit with assertion failures and be identified as detected behaviorally.
A compile/dependency error is not a successful negative control. Requirements
remain JDK17+ with a real compiler, Kotlin2.0.20, and the pinned DexKit2.2.0 class
JAR supplied through `WAEX_QA_DEXKIT_JAR`. This isolated JVM fixture uses explicit
Android/Xposed boundaries; it does not send receipts or verify a real account.

Historical validation of PR #200 (not a new current-nightly result): the merge was exercised on Linux with Python3.12.14, Temurin21.0.13.1+2 and
Kotlin2.0.20. The current production fixture completed fourteen scenarios and
400 internal checks without failure. All five mutants completed with behavioral
failures; a separate last-case resume completed one of five and correctly
reported `full_matrix=false`. These are fixture results, not installed Android
or WhatsApp compatibility. New remote heads still require current CI/review.

## Current-nightly reconciliation

The resume runner and selection controls are carried onto `nightly@c089458569564c241e6e2cddbd5a4de301299f28`.
Production callbacks remain unchanged. The retry fixture now extracts the current
instance sender, production constructor and enqueue/ledger helpers. It compiles
the real BaseFeature and shared privacy layer, preserves all fourteen original
scenarios, and incorporates the constructor boundary from the focused current
manual-receipt reconciliation instead of reconstructing it in the test wrapper. Three additional cases
verify that active delivery, Ghost Mode and per-contact vetoes block before
enqueue without consuming pending recipes. The persistent ledger boundary is
explicitly empty; this does not validate database persistence or ledger replay.

The current source passed 17 scenarios / 424 checks. All five mutants compiled
and completed all 17 scenarios, with 7, 4, 9, 13 and 2 assertion-failing scenarios.
A separate last-case resume completed one of five and reported full_matrix=false.
Five selection tests passed. Source hashes identify these current local results
separately from the historical measurements above; no resumed suffix is counted
as a full matrix. Android/Xposed lookups remain controlled JVM boundaries.
