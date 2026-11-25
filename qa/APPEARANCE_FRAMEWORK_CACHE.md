# Appearance framework dependency preparation

Appearance run `45589665365`, attempt `1`, at commit
`68be03ba7346fff9417720ea4c775ed2d798809a` restored and verified all three
instrumented SDKs without HTTP requests. Floating then stopped before compilation
because Maven could not obtain its dependency plugin: the logs record HTTP 429 for
the Central prefix metadata and `maven-dependency-plugin:3.8.1` POM. The three Maven
invocations consumed 188.935391 seconds. No Android test initialized. This is an
infrastructure result, not a failure of the Floating or Channel assertions.

## Permanent recovery on a cache miss

`prepare_framework_dependencies.py` selects the 36 `deps` entries from the existing
`framework_dependency_lock.json`. It uses their exact URLs, byte counts and SHA-256
identities. It does not resolve a POM, Maven plugin or transitive graph. The real
native runtime remains required. The existing lock is unchanged.

The two AAR entries retain both identities already in that lock: the container and
its extracted `classes.jar`. The helper additionally bounds those containers by
their verified sizes, 5,441 and 103,877 bytes. It accepts exactly one unencrypted
`classes.jar` with the pinned size and digest, and publishes only verified bytes.

The helper reuses the existing SDK downloader and process supervisor unchanged:
at most three attempts per file, a 30-second socket/retry-wait ceiling, the same
transient status set, and a 180-second total worker deadline by default. A server
Retry-After beyond the available budget ends explicitly without an early retry.
The supervisor closes the worker before hashing its log and removing its recorded
temporary files. Integrity failures are not retried.

All selected existing destination/cache inputs are checked before requesting an absent one.
Receipts, worker logs and pending receipts must resolve outside the destination
and cache directories. API, supervisor and CLI reject conflicting paths before
creating directories or launching a worker, including sidecar symlink aliases.
Unexpected files, symlinks, corruption and missing offline inputs reject the
preparation. A failed identity check never triggers network recovery. An absent
cache can be rebuilt from the lock's public URLs; this permanent path has no
dependency on a historical CI artifact or its retention period.

The workflow restores the exact cache key
`waex-framework36-${runner.os}-${hashFiles('qa/framework_dependency_lock.json')}` at
`$RUNNER_TEMP/waex-appearance-hooks/framework-deps`. It saves only a completely
verified graph before starting consumers, and rehashes that graph offline after
all attempted consumers. There are no prefix restore keys or ignored failures.

Floating, its six causal mutants, Channel and its eleven mutants receive that same
directory through `--deps`. Core 1.18.0, Annotation 1.9.1, DexKit 2.2.0 and the
verified Kotlin 2.0.20 standard library remain the other four pinned classpath
inputs. The three instrumented SDKs remain separate and offline. Test denominators,
assertion maps and production sources are unchanged: Floating 81 and Channel 75.
Floating retains its documented three declaration-only source projection; this
does not establish complete-hook or private-interface compilation.

## One-off cache seeding

`appearance-framework-cache-seed.yml` runs automatically only when its own path is
pushed on `integration/android-matrix-nightly8-20261124`; it also permits an explicit
manual invocation on that branch. One automatic push requires no second dispatch.
It is separate from the previous SDK seed workflow.

The seed downloads `hma-framework-dependencies-45581309675-1` from producer run
`45581309675`, attempt `1`, source `dca0283d759e367580babec4bd93955ce01dc716`.
It records this historical producer separately from the current consumer identity.
Before staging any cache entry, it verifies all 39 files and the exact bundle
manifest digest `d98dc65bf3699143d04f82fc2e96528a98ccf36ff907d74b3165662e2cc1489d`.
Only its 36 dependency JARs are copied into the dependency cache.

After save, the seed removes its staged files, requires an exact cache hit at the
same path/key, and rehashes all 36 restored JARs offline. It rechecks the original
39-file bundle as well. Its receipt requires both preparations to close with zero
requests, all action outcomes to succeed, and `cache-hit` to be exactly true.
The seed does not execute Android tests. A seed failure does not replace the
permanent public-URL recovery path.

## Verification boundaries

The new 17 loopback controls cover the cold 36-URL graph, both AARs, warm and offline
reuse, corruption before HTTP, wrong containers/extracted members, duplicate
members, incomplete native runtime, Retry-After, slow-body process cleanup and
18 evidence-path subcases requiring rejection without any filesystem writes.
These are synthetic transport fixtures, not Android SDK executions. The existing
13 SDK transport controls retain their separate scope. Canonical dependency runs,
local protocol qualifications and actual GitHub cache receipts must be identified
separately; a local simulated cache transport cannot certify a GitHub cache hit.
