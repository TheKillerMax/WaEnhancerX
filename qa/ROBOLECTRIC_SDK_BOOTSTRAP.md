# Bounded preparation of Robolectric SDKs

`prepare_robolectric_sdks.py` prepares the three SDK entries already defined by
`framework_dependency_lock.json`. It imports the existing lock parser and exact
size/SHA-256 verifier from `framework_dependency_bundle.py`; there is no second
SDK version list. The lock's other 36 framework dependencies remain owned by the
existing producer. Channel reuses that producer's graph and public API jars.

## Identity and cache rules

- Every selected existing destination/cache file is checked before any missing
  SDK can start a request. Incorrect identities stop immediately, even if a good
  alternate cache or a network endpoint is available.
- Offline mode rejects missing entries without a request. Verified cache bytes
  are linked where possible, with an exclusive copy fallback across filesystems.
- Downloads stay in owned partial files until their complete byte count and
  SHA-256 match the canonical lock. Publication is exclusive and never replaces
  an existing destination.
- A worker timeout closes the worker before the parent hashes its log and
  removes registered partial files. It does not remove verified SDK entries or
  unrelated cache contents. Consumers start only after an accepted receipt.

The workflow cache key includes the entire canonical lock hash, has no fuzzy
restore prefix, and is still checked after restoration. The existing HMA bundle
helper and Source QA workflow are unchanged.

## Time and retry limits

The default whole-worker budget is 180 seconds, with an allowed maximum of 600
seconds from the existing Maven helper's limit. A serial SDK download uses at
most three attempts, sharing that helper's attempt ceiling. Only transient
transport failures and HTTP 408/429/500/502/503/504 are eligible. Identity,
oversize, certificate, ordinary HTTP and malformed Retry-After errors do not
receive a download fallback.

Numeric and HTTP-date Retry-After values are respected. A server wait longer
than the remaining budget or the 30-second single-wait ceiling is recorded as
deferred failure; no earlier retry is issued. The worker checks its monotonic
deadline between `read1` calls. A separate process deadline also closes a body
that keeps trickling bytes without triggering a socket timeout. Linux uses the
already reviewed PR98 process-group watchdog. The Windows SDK worker starts no
child processes and is killed and reaped with a bounded wait.

The worker deadline can include bounded process cleanup after the requested
budget. Receipts record both the requested deadline and measured supervisor
elapsed time; they do not promise exact wall-clock equality.

## Verification scope

Thirteen controls use a real loopback HTTP server with explicitly synthetic
small bodies. They cover transient 429 and 503, nonretryable 404, numeric and
date Retry-After, invalid Retry-After, wrong hashes, oversize responses, corrupt
cache/destination preflight, verified offline reuse, offline absence and a
continuously trickling response. The slow-body test imposes a 0.4-second external
deadline against a worker whose internal budget is 60 seconds and checks that
the worker is closed and no partial or final JAR is left. These are transport
controls, not Android runtime tests.

A separate canonical-lock run verified all three real SDK artifacts with zero
requests, using lock SHA-256
`8fa74776e9ef20fdee5773a058235c4d0203a750cba1a4f9aed8d2d4e4e8924f`.
Positive and mutation Android consumers use Robolectric's offline SDK directory
setting. New source pins and results are recorded separately from the original
public HTTP 429 artifact.

```bash
python3 qa/test_prepare_robolectric_sdks.py --out "$QA_OUT/sdk-controls"
python3 qa/prepare_robolectric_sdks.py \
  --out "$QA_OUT/sdk-jars" --report "$QA_OUT/sdk-bootstrap.json" \
  --cache "$VERIFIED_SDK_CACHE" --offline
```

Use fresh report/output paths for independent attempts. A cold public run still
depends on repository availability and the existing framework producer. A
server-mandated wait beyond the bounded budget must remain a clear infrastructure
failure, not a passing Android result or an aggressive retry loop.
