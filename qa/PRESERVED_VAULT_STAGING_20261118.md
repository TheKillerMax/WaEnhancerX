# Preserved vault: stage production diagnostics and keep 33 Android SQLite checks

Base: `main@0aaffab0270a3d0832bef2895f6457f3792fd74a`.

## Reproduced regression

GitHub Actions *Source and JVM regression checks*, preserved-vault job
https://github.com/WaEnhancerX/WaEnhancerX/actions/runs/44248788801/job/134614098362
failed while compiling the unchanged `PreservedMessageStore.kt`:
`unresolved reference: com.waenhancer.xposed.utils.HookErrors`.
The old `qa/android_preserved_store_test.py` only staged
`ContactIdentityPolicy.java` and `PreservedMessageStore.kt`, omitting the
actual production diagnostic dependency. The fixture never reached Android
SQLite behavior; this was a QA source-closure failure, not evidence that
message preservation itself was defective.

## Scoped repair

- Stage unchanged **production** `xposed/utils/HookErrors.java` and compile it
  alongside `ContactIdentityPolicy.java`. Do not replace its error accounting,
  throttling, or exception handling with a fake.
- Supply only the required external compile boundaries:
  `androidx.annotation.NonNull`, `VisibleForTesting`, and a diagnostic
  `XposedBridge.log(String)` sink. The sink refuses null messages and records
  values; no hook registration, provider, or permission bypass is simulated.
- Record SHA256 for production sources and all generated adapters.
- On Windows, launch the **same installed Kotlin compiler jars** via JDK when
  the `kotlinc.bat` wrapper would split a semicolon-delimited classpath.
  Linux/macOS retain `kotlinc`. This is a platform invocation fix, not a
  fallback to a different compiler or weaker test.

## Executed acceptance

**PASS:** Windows 11 WAEX-Lab, JDK 17.0.20.1, Kotlin 2.0.20,
Robolectric 4.17 (Android API 24/28/34), real SQLite files and unchanged
`PreservedStoreCompatibilityTest.java`. After staging, `javac-production`,
`kotlinc-production`, `javac-tests` and JUnit all exit 0. **33/33 tests,
0 failures, 0 assertion failures, accepted_result=true**.

Reproduction with previously acquired verified Maven JARs:

```powershell
$env:JAVA_HOME='C:\WAEX-Lab\tools\jdk17'
$env:PATH='C:\WAEX-Lab\tools\kotlin-2.0.20\kotlinc\bin;C:\WAEX-Lab\tools\jdk17\bin;'+$env:PATH
python qa/android_preserved_store_test.py --source-root C:\WAEX-Lab\work\preserved-vault-qa-20261118 --out C:\WAEX-Lab\evidence\waex-preserved-vault-20261118\candidate-02 --deps C:\WAEX-Lab\evidence\qa-current-source-fixtures-20261113\preserved-dispatch-r1\deps --maven-repo "$env:USERPROFILE\.m2\repository"
```

Evidence `candidate-02/result.json`, `junit.log`, compilation logs and
`dependency-sha256.json`. Source fingerprints:
`PreservedMessageStore.kt` SHA256
`dbc76e1bf3cbfb0b76c1ef7c0a63972aa7fd1d8e6721a2323f2825fb09932894`;
`HookErrors.java`
`fdb560198f8918bdfa2649c2fa1a925d7c534ec8e11947c5dae4cad9f0df6f0e`;
test fixture `PreservedStoreCompatibilityTest.java`
`9233ad77505d90d8b957e01349d4a5de2581d4f3d98bcdddb2e7dd874ceaadd5`.

Baseline negative condition **FAIL** (missing HookErrors at source compile) was
observed in CI; no behavioral negative mutant was executed for this patch.
The tests cover historical schemas, SQLite lifecycle and row-key expression
under Robolectric, **not** capture hooks, installed WhatsApp, LSPosed or
the full Compose vault UI. CI acceptance for the proposed branch remains
**NOT_VERIFIED** until a PR run on its exact SHA. Revert only this QA repair
if its verified sources or compiler contract no longer match.

No production application file, user/account, WAEX APK, WhatsApp data,
signature or license was changed.