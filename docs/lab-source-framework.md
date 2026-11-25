# Sequential public framework lab

This isolated fork experiment addresses the dependency HTTP 429 failures observed
in source-qa run 45519549262. It checks out WAEX commit
`c52f064bad7ba32445f8515bc2f0421618438975` and runs the existing public runners,
fixtures, expectations and default Android SDK sets without edits. It does not
change the regular source-qa workflow, project Gradle, product code or declared
Android compatibility. This new workflow/controller is a protected R5 proposal
for maintainer review; it does not waive repository approval rules.

## Execution and acceptance

One Ubuntu 24.04 job runs acquisition and these gates sequentially:

| Gate | Required result |
| --- | --- |
| Renderer runner controls | 19 host controls |
| Presence renderer | 90 positive cases, APIs 28/34/36; 3 focused mutants rejected |
| Presence companion | 15 behaviorally rejected mutants, 30 scenarios each on API 34 |
| Preserved store | 33 positive cases, original defaults |
| Preserved dispatch | 105 positive cases, original defaults |
| Runtime resources | 12 cases, 22 resource contexts, 7 locale tests |
| Interface scale | 12 cases on APIs 24/28/34 |
| Stability | Default all mode: 12 updater + 3 filter cases together |

Every process must succeed. Fresh JUnit files must report the exact count with
zero failures, errors or skips; testcase counts must agree with their summaries.
The existing renderer runners also require behavioral rejection, not compilation
or framework-initialization failures, for their mutation controls. The controller
additionally checks completeness of those receipts. No enabledSdks filter,
selected-SDK argument or negative-acceptance argument is introduced.

The source commit, clean index and every tracked file's mode/bytes/SHA256 are
captured before and after testing. The preinstalled Kotlin CLI must report 2.4.21,
the version observed in the original Linux CI log. The actual compiler path,
compiler JARs, JDK versions and Android SDK inputs are recorded. JDK 21 and Python 3.11
are selected by pinned official actions. The source's Gradle 9.1.0 distribution
checksum remains enforced by its original wrapper. No full WAEX APK, private
licensing module, device, WhatsApp account or LSPosed execution is involved.

## Acquisition and cache

The SDK union is exactly APIs 24/28/34/36, totaling558,916,341 bytes. Its four
instrumented JARs are pinned to official Maven Central SHA512 sidecars. The shared
Maven closure is checked against the three unchanged runner POMs, then acquired
once with Maven strict checksums and the existing dependency plugin 3.8.1. Only
official Central/Google repositories from those POMs are used; an isolated empty
settings file prevents inherited mirrors or credentials. Existing runner --deps
and SDK-directory arguments reuse those dependencies. Robolectric resolves SDKs
locally through dependency.dir/offline properties, without narrowing tests.

The native-runtime JAR is verified against its official SHA512 after Maven
resolution. JUnit/Hamcrest SHA256 pins are derived from bytes matching official
SHA1 sidecars and HEAD sizes: those historical artifacts have no SHA512 sidecar.
DexKit and the two public 2.0.3 APKs retain the already-reviewed runner SHA256 pins.
These APKs are public test inputs, never installed or committed by this job.

A verified cache hit makes no direct HTTP request. A missing pinned artifact
gets one bounded request chain, with redirects restricted to official origins.
HTTP 429 records status/Retry-After and stops; it does not retry, rotate mirrors or
relax checksums. The owned process tree is also stopped when a Maven/Gradle log
reports 429. Later stages become explicitly BLOCKED. Cold-cache resolution can
still fail if the public service remains rate-limited; that is an infrastructure
FAIL, never a test PASS. Maven's internal client may emit more than one request
before logging an error; the controller makes no second resolution attempt.

The action caches only dependency storage, never previous test results. Its
manifest covers every cached file and is verified before use; altered, missing,
additional or symlinked files fail closed. Gradle's modules-2 and wrapper cache
are restored into a new runtime directory; locks/gc/temp files are excluded when
sealing the next successful cache. The pinned action saves caches only after a
successful job; a cold failed run preserves diagnostic receipts but cannot
bootstrap a reusable cache. A later attempt still requires service recovery. Maven artifact provenance metadata remains in
the cache. The cache manifest proves equality to a prior successful run; official
pins/checksum verification provide the separate artifact-provenance checks.

The controller reserves 10 GiB on its disposable Linux runner. It neither downloads
to the Windows lab nor changes that machine's separate 20 GiB reserve. Evidence is
uploaded as text logs/JSON/XML on both success and failure. No cache JAR, APK,
credential, signing key or generated build binary is included in that artifact.

## Primary references

- [Sonatype 429 guidance](https://central.sonatype.org/faq/429-error/)
- [Robolectric dependency-directory configuration](https://robolectric.org/configuring/)
- [Maven settings/checksums](https://maven.apache.org/settings.html)
- [Gradle cache format and copying](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [GitHub cache scope](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [setup-java 6.3.0](https://github.com/actions/setup-java/commit/d1374f8ac74474200d16ef8ecee22c7ae7a51880)
- [setup-python 6.2.0](https://github.com/actions/setup-python/commit/a309ff8b426b58ec0e2a45f0f869d46889d02405)

Run host-only counterchecks with `python3 qa/test_source_framework_lab.py`.
They exercise cache corruption, checksum failures, single-attempt429 handling,
owned-process termination, incomplete/failed/skipped JUnit reports and explicit
blocked stages. They do not substitute for execution of the real Linux job.

## Supervisor v2 review

The controller enables Linux PR_SET_CHILD_SUBREAPER for each single sequential
command and requires no preexisting child process. Detached descendants that
outlive their immediate parent are reparented to this controller, identified by
PID and start tick, terminated and reaped. Cleanup must finish before PASS; the
previous subreaper setting is restored. This closes the independently reproduced
v1 escape where a child detached and reparented between polling intervals.

Each changed log is reread from byte zero with a 16 MiB bound, including one final
check after process cleanup. Truncation or inode replacement cannot leave a stale
offset masking a later persistent HTTP429 marker. Five new host counterchecks
cover immediate detach, preexisting-child refusal, truncation, replacement and
429 on immediate exit. The v1 evidence is preserved separately.

These v2 counterchecks have not executed yet: the Linux scratch environment
disconnected before this revision. Python3.11 AST validation on Windows is only
syntax validation, not process, network, JVM, Android or CI evidence.

[Linux child-subreaper contract](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html)
