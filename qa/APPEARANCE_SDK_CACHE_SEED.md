# One-off Appearance SDK cache seed

The Appearance run `45581197614`, attempt `1`, at
`dca0283d759e367580babec4bd93955ce01dc716` stopped before its Android consumers.
Its first SDK request returned HTTP 429 with `Retry-After: 79681`. The bounded
resolver correctly deferred that request. All 13 transport controls passed;
Floating, Channel and the resource gate did not start in that run.

This infrastructure workflow reuses the dependency graph that Source QA had
already produced. It does not contact Maven, change a retry interval, or change
the Appearance, Source QA, Android product or test sources.

## Explicit provenance

| Identity | Pinned value |
| --- | --- |
| Source QA producer run / attempt | `45581309675` / `1` |
| Producer head | `dca0283d759e367580babec4bd93955ce01dc716` |
| Producer artifact | `hma-framework-dependencies-45581309675-1` |
| Bundle manifest SHA-256 | `d98dc65bf3699143d04f82fc2e96528a98ccf36ff907d74b3165662e2cc1489d` |
| Framework lock SHA-256 | `8fa74776e9ef20fdee5773a058235c4d0203a750cba1a4f9aed8d2d4e4e8924f` |
| Bundle content | 36 framework JARs and 3 SDK JARs; 685,831,012 bytes |
| Cache path | `${{ runner.temp }}/waex-appearance-hooks/sdk-jars` |
| Cache key | `waex-sdk3-${{ runner.os }}-${{ hashFiles('qa/framework_dependency_lock.json') }}` |

The producer and HMA consumer receipts agree on these 39 identities. The seed
performs its own verification after the artifact is downloaded in CI. The seed
receipt records its current run, attempt, head and branch separately from the
historical producer. It does not relabel historical bytes as a same-run bundle.

The UI-reported artifact ZIP digest is
`bd64dc9ea4b45a90c43628755f93286e4169f7b74704ea34a5ca8d0ff94f917d`.
That ZIP has not been downloaded to the local workstation for a second digest.
The seed verifies the downloaded manifest and all 39 extracted byte identities;
it does not claim an independent rehash of the compressed artifact ZIP.

## Execution and acceptance

The initial push trigger is restricted to
`integration/android-matrix-nightly8-20261124` and a change to
`.github/workflows/appearance-sdk-cache-seed.yml`. A newly added workflow must
not depend solely on manual dispatch being available on a nondefault branch.
Manual dispatch is also declared, but the job rejects any other branch.
The existing Appearance push trigger can run concurrently; that separate run
does not count as validation of the seed and can still encounter a cold cache.

Before the cache is written, the workflow checks the unchanged verifier,
resolver, supervisor and Appearance workflow pins, then verifies the complete
39-file bundle with the historical run, attempt and head. It also requires the
exact manifest digest. Only then does the existing resolver stage the three
SDKs with `--offline` and zero Maven requests.

The cache uses the identical Ubuntu runner, path and key expression as
Appearance, with no prefix fallback. After the save action, the seed removes
only its own three staged links, requires an exact restore hit and rehashes all
three restored files offline. This detects an unavailable save or a preexisting
cache entry with incorrect bytes. Cache entries are not silently replaced and
incorrect identities do not trigger a network fallback.

The job has a ten-minute bound, and the artifact download step has a five-minute
bound. An expired or unavailable source artifact fails explicitly. No alternative
source, fresh Maven download, partial native runtime or relaxed oracle is used.
The original source artifact has one-day retention, so this fixed seed is a
recovery procedure for the identified run, not a permanent dependency service.

Acceptance requires `result.json` to report `accepted: true`, verification of
all 39 files, zero Maven requests in both SDK receipts, `cache-hit: true`, and
successful offline verification of the restored three SDKs. A green cache-save
step alone is insufficient. The artifact preserves context, verification,
supervisor logs and the final result, without republishing the JARs.

After a successful seed, rerun Appearance run `45581197614` at the original
`dca0283d759e367580babec4bd93955ce01dc716` code. Audit the new attempt's actual
cache hit, SDK identities, 13 transport controls, 81 Floating tests, six Floating
mutants, 75 Channel tests, eleven Channel mutants and resource gate separately.
The seed itself exercises no Android behavior. Its local qualification cannot
establish that GitHub cache storage or the later Appearance run succeeded.
