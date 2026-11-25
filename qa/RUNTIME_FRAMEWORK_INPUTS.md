# Reusing verified Runtime framework inputs

Source QA run `45581309675`, attempt `1`, at
`dca0283d759e367580babec4bd93955ce01dc716` compiled the Runtime product and test
sources but stopped before JUnit. Gradle received HTTP 429 while fetching
`org.robolectric:nativeruntime-dist-compat:1.0.19`. The same run's existing
framework producer had already verified that artifact and the three SDKs.

The Runtime, Vault and Profile jobs now depend on that producer. Each downloads
the artifact named for its own run and attempt, then verifies all 39 locked
files and the explicit run, attempt and source head. A missing or invalid
artifact fails the consumer; it does not trigger an alternative dependency
download. The producer, framework lock and behavioral expectations are unchanged.

## Runtime's Gradle contract

`qa/verify_runtime_framework.py` accepts these four options together:

```text
--framework-bundle PATH
--bundle-run-id RUN_ID
--bundle-run-attempt ATTEMPT
--bundle-head-sha COMMIT
```

`qa/runtime_framework_inputs.py` validates the complete bundle before the
runner retrieves its public APK fixtures. It creates a local Maven repository
containing the exact native runtime JAR and its original, hash-pinned POM.
The checked-in POM retains the published coordinates and metadata. It has no
parent or dependencies; the helper rejects a changed metadata contract.

Gradle's exclusive repository filter covers only
`org.robolectric:nativeruntime-dist-compat:1.0.19`. Other modules retain the
existing Google and Maven Central repositories. No partial native runtime,
replacement classes, generated dependency metadata or broad repository override
is introduced.

Before the test task runs, Gradle must resolve exactly one native artifact with
the expected version, length of 159,144,356 bytes and SHA-256
`33e0a0982b3ba599763af250b86eb8d67ab6c186c2fa2c5e823ee003bdcd4ed8`.
The callback records the actual resolved file. Robolectric uses the bundle's
three verified SDKs with offline resolution enabled. After the unchanged test
acceptance checks, the helper verifies the entire bundle again.

Without the four bundle options, the existing standalone runner behavior is
preserved. `--offline` remains a separate option for existing local Gradle and
public-APK caches. Supplying a framework bundle alone does not claim that every
Gradle plugin, Android tool or public APK is already available offline.

## Evidence and interpretation

After the workflow verifies the CI origin, `qa/test_runtime_framework_inputs.py`
checks incomplete CLI identities, the original POM and disposable receipt
failures. These controls cannot establish that Gradle used the JAR; the native
framework execution and its actual Test classpath receipt remain required.
Only their small result and log are uploaded, not the temporary JAR links.

The Runtime artifact preserves the workflow's bundle verification receipt,
`framework-inputs-before.json`, `gradle-native-resolution.json`, the final
`framework-inputs.json`, source identities, compilation logs and JUnit evidence.
A successful input receipt does not substitute for the original behavioral
acceptance checks. A host qualification using a locally reconstructed bundle
must label its producer identity as synthetic and must not claim a CI download.

The original JUnit fixture remains unchanged. These tests exercise public
utilities and Android framework/resource behavior; they do not establish full
WAEX, private licensing, WhatsApp/LSPosed, ART on every version, or a physical
device's DSU recovery.

The native POM is preserved from its published Maven coordinate:
<https://repo.maven.apache.org/maven2/org/robolectric/nativeruntime-dist-compat/1.0.19/nativeruntime-dist-compat-1.0.19.pom>.
Its byte identity is checked before repository creation and after copying.
