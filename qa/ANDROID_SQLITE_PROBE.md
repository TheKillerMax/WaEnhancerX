# Neutral Android SQLite lab probe

This is a self-instrumenting, permission-free QA application for **new, disposable
x86_64 Android emulators**. It is not the WAEX application, WhatsApp, a provider
authorization test, or an LSPosed test. Never install or run it on the Motorola
or another personal device. The earlier blocked P356 phone operation remains
untouched; this candidate has a different package and an emulator-only scope.

## Origin and changes

The owned P356 builder source was inventoried at
`C:\WAEX-Lab\android-research-20261123\bin\P356_android_gallery_bench.py`:

- Source: 14,582 bytes, SHA-256
  `afa58afa8742f948840c79cf2474a1b44341f3a1f981dbf4e823ad7e875df688`.
- Its embedded Java: 10,935 bytes, SHA-256
  `fd13d2888357a8dbf52258d4c25ce7fb96cae8d3ba9746de9214da4389cf43f9`.
- The historical APK hash is not a current build artifact. Its signing key was
  ephemeral; a new build gets a new signature and APK hash.

This candidate retains the 50,000 / 100,000 / 150,000 synthetic rows, page size
96, 20% NULL timestamp fallback, tied timestamps, 24 balanced timing trials per
query, equality/edge/insertion/anchor-deletion oracles, private database and
cleanup. It changes minSdk to 24 and targetSdk to 36, replaces the Termux UID
builder with existing SDK/JDK tools, and uses `org.lab.waex.qa.sqlite`.

The old row-value comparison requires SQLite 3.15. Android's API documentation
lists SQLite 3.9 for API 24 and 3.18 for API 26; vendors can differ. Both seek
predicates now use the equivalent scalar expression:

```sql
sort_ms < CAST(? AS INTEGER)
OR (sort_ms = CAST(? AS INTEGER) AND _id < CAST(? AS INTEGER))
```

The timestamp parameter occurs twice. The expression-index variant uses the
same comparison over `coalesce(taken_ms,added_ms)`. Expression indexes are
available from SQLite 3.9. The query-plan and timing results are descriptive;
there is no speedup threshold or assumption that every version uses SEARCH.

Primary references:

- <https://www.sqlite.org/rowvalue.html#backwards_compatibility>
- <https://www.sqlite.org/expridx.html>
- <https://developer.android.com/reference/android/database/sqlite/package-summary>

## Build once

Use the existing official platform 36 and build-tools 36.0.0 with JDK 17+ and
Python 3.11+. No Gradle, private source, dependency download, production signing
key, SDK installation or license acceptance is performed by this builder.

```sh
python3 qa/build_android_sqlite_probe.py \
  --sdk "$ANDROID_HOME" --java-home "$JAVA_HOME" \
  --out "$RUNNER_TEMP/waex-sqlite-build"
```

The output directory must be new. Successful output is
`build-result.json: status=PASS_BUILD_ONLY`, `ephemeral_key_absent=true` and
`sqlite-probe.apk`. The report records APK/DEX/source/tool SHA-256, min/target SDK,
commands, signature verification, archive integrity and absence of native
libraries. The APK has `testOnly=true`, no requested permissions, no exported
app components, backup disabled, cleartext traffic disabled and no Activity.
Its sole component is:

```text
org.lab.waex.qa.sqlite/.SqliteProbeInstrumentation
```

Keep the resulting APK immutable and use **that exact SHA-256 in every matrix
job**. Build reproducibility here means an explicit recipe and recorded inputs;
fresh ephemeral signing does not promise identical signed APK bytes across
independent builds. Upload only the APK, build-result and necessary reports, not
the workspace or signing material. The key is removed in the builder's finally
block, including failures.

## Runtime handoff to the isolated emulator controller

The separate lab controller must first verify its fresh AVD ownership, exact
emulator serial, KVM acceleration, completed boot, expected API/ABI and page-size
mode. It must verify the downloaded build artifact hash and that this package
is absent before installation. These scripts contain no adb/device operations.

On that verified AVD only, install with `adb -s "$LAB_SERIAL" install -t` using
the exact APK path. Generate a new 32-character lowercase hexadecimal nonce,
then invoke:

```sh
adb -s "$LAB_SERIAL" shell am instrument -w -r \
  -e run_nonce "$LAB_NONCE" \
  org.lab.waex.qa.sqlite/.SqliteProbeInstrumentation
```

Capture the complete raw output, command status and wall time. A zero adb exit
status alone does not establish success. Readback of the newly installed base
APK and SHA comparison is recommended before execution where supported.

```sh
python3 qa/validate_android_sqlite_probe.py \
  --log "$PROBE_LOG" --expected-nonce "$LAB_NONCE" \
  --expected-api "$LAB_API" --expected-page-size "$LAB_APP_PAGE_BYTES" \
  --out "$PROBE_RESULT"
```

The validator requires exactly one receipt, final instrumentation code -1,
matching nonce/environment, the complete workload, **280 successful assertions**
and removal of the owned database. It rejects failed/duplicate results, stale
nonce, wrong API/ABI/page mode, missing assertions and inconsistent timing
summaries. All queries operate on the package's cache database. The app refuses
a pre-existing fixture database and never deletes such a file. It also checks
its own package/UID, test-only flag, x86_64/64-bit process and emulator hardware.
The workload has a 150-second internal budget; the controller needs an external
timeout (for example 240 seconds) and must preserve failures rather than retry
them as successful runs. Cleanup/uninstall is restricted to this owned package
on that disposable AVD.

## Page size and acceptance limits

`application_page_size_bytes` comes from
`android.system.Os.sysconf(OsConstants._SC_PAGESIZE)`; `sqlite_page_size_bytes`
comes from `PRAGMA page_size`. They are different measurements and need not be
equal. On the x86_64 ps16k image, Google documents simulated 16 KB behavior for
applications while the kernel uses 4 KB pages. Do not label that result a test
on an ARM kernel with native 16 KB pages:
<https://android-developers.googleblog.com/2024/08/adding-16-kb-page-size-to-android.html>.

A passing result establishes only that this neutral Java/SQLite workload and
its cleanup passed on the recorded emulator environment. There is no native
ELF payload, Binder/provider permission probe, cross-UID isolation test,
MediaStore, account, network, Google Photos, full WAEX, WhatsApp or LSPosed test.
The recorded own UID is metadata, not an authorization or identity-security
test. Emulator timings do not establish real-device performance gains.

Host controls can be run before publishing the lab:

```sh
python3 -m unittest discover -s qa -p test_android_sqlite_probe.py -v
```

Those tests use explicitly synthetic receipts and host SQLite. They do not
constitute Android API 24 or ps16k runtime evidence. The initial real pilot
should be API 24 plus API 35 ps16k after the separate preflight has succeeded.
