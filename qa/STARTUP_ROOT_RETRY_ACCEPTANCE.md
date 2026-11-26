# Explicit root retry refresh

The manager's `Check again` action previously reused a root-access result cached
for 60 seconds. Approving superuser access after a failed initial check could
therefore leave the next explicit retry showing the cached denial.

`MainActivity` now passes the existing `forceRefresh` argument when
`rootCheckAttempt > 0`. The initial launch still accepts the result transferred
from `PermissionsActivity` and retains the ordinary cache behavior. Root command
execution and its permission checks are unchanged.

## Focused executable check

Use an existing JDK and complete Kotlin distribution; no downloads are performed:

```bash
python3 qa/test_startup_root_retry.py \
  --source-root . \
  --java /path/to/jdk/bin/java \
  --kotlin-home /path/to/kotlinc \
  --out /new/output/directory
```

The test extracts the actual cache region from `UpdateDownloader.kt` and the
exact root invocation inside `LaunchedEffect(rootCheckAttempt)`. It also checks
the initial handoff guard and the retry counter callback. Only elapsed time and
the root-command response are controlled boundaries.

With Kotlin 2.0.20, JDK 21 and JVM target 17, the nightly9 baseline completed all
six scenarios and failed three freshness contracts. The candidate completed all
six with no failures. The decisive regression changes a denied root response to
a granted response before cache expiry: the explicit retry must issue a second
command and observe the new result. Ordinary positive/negative caching and the
exact TTL boundary retain their behavior. Forced-probe revocation/failure cases
also check that a fresh failed probe does not reuse a cached grant; those are
probe contracts, not assertions that the retry button is visible in every UI state.

To reproduce the negative control, provide the baseline `MainActivity.kt` from
`c089458569564c241e6e2cddbd5a4de301299f28` with `--main-source`. Compilation must
succeed, `ROOT_RETRY_CASES=6;FAILURES=3` must be present, and execution must fail.

This is Kotlin/JVM execution of extracted production logic. It does not execute
Android, Compose lifecycle, `su`, licensing, networking or installation, and does
not build the complete APK. Existing physical manager startup evidence is
separate from this candidate and is not claimed as its acceptance.
