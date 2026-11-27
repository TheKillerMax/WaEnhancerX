# Delete-for-me preservation availability

## Standalone check

From the root of the matching checkout, choose a fresh output directory and run:

    python3 qa/android_preserved_dispatch_test.py --out <fresh-output>

The standard runner uses public Maven dependencies. Verified offline runs also
supplied `--deps`, `--sdk-jars`, `--dexkit` and `--locked-inputs`. The observed
local toolchain was JDK 21 with Kotlin CLI 2.0.20. The four recorded hosted
artifact identities for Kotlin 2.4.21 are accepted as provenance; they do not
establish that either tree ran on that CLI.

Local case counts are totals across Robolectric APIs 24, 28 and 34:

- A3 (`d3ccec442b3d7c8981a177e01bde54303eef304a`): 105 Dispatch cases.
- B3 (`bbc0467405bea4e2337fec832d6eeee6c135d673`): 123 Dispatch and 30 Origin
  cases. Both positive suites completed with zero failures and zero skips.

Dispatch receipts are `result.json` and `junit.log`; Origin receipts are
`origin-result.json` and `origin-junit.log`. On B3 each intentional mutant
failed exactly the three SDK variants of its corresponding method, while the
other suite completed.

## What the checks establish

Preservation needs an installed Delete-for-me entry point. Legacy entry points
only open a scope and also require database interception. Out-of-scope capture
is refused. A failed partial installation leaves preservation unavailable and
the registry removes the hooks already installed.

When optional SQLite interception failed or installed no hooks, the positive
direct-copy check used a synthetic, issued local request. A shared Runnable or
a stale cached method alone cannot authorize capture. An unresolved message
key leaves preservation unavailable; the product still supplies `keys=null`
for the modern graph. Seeing the same instance or observing a synchronous API
call does not prove that a local request was issued. Matching a database row
and persisting a message through the manager are also distinct checks; neither
establishes the origin of the request.

These local results do not establish native DexKit discovery, ART/LSPosed
execution, physical-device behavior or WhatsApp Personal/Business
compatibility. Official exact-commit R13 acceptance remains pending.

## Historical C03 reproduction only

The historical extension added six Dispatch methods on three SDKs, taking the
suite from 105 to 123 cases. B3 already runs all 18 added cases without a patch.
To reproduce the older result, retrieve the public archive and check its SHA-256:

    archive=$(mktemp)
    git show 41a073756f3e85573eaa0fd875fb18c85ca0365b:qa/preserve-availability-fixtures.patch > "$archive"
    printf '%s  %s\n' 84e0abef31130e03b58ec5729147f64442fcdc34ee5883e2559704d936609099 "$archive" | sha256sum -c -

Both file preimages match C03 QA commit `f0c1c47b656fae73554b9dc057d0bb2f22db7929`
(tree `a89fd0d34d97be0bd6ff1cb101cda8faacfc8a28`). Only after a checksum match,
run `git apply "$archive"` in a scratch copy of that C03 commit. Run both commands
below from that patched QA directory. Use a separate checkout of F
(`41a073756f3e85573eaa0fd875fb18c85ca0365b`) as the candidate source root for
123 passes, and an unmodified C03 source root for the 12-failure negative control:

    python3 qa/android_preserved_dispatch_test.py --source-root <F-checkout> --out <fresh-positive-output>
    python3 qa/android_preserved_dispatch_test.py --source-root <unmodified-C03-checkout> --out <fresh-negative-output> --expect-assertion-failures 12
