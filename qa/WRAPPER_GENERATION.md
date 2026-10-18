# Gradle wrapper generation and verification

The project selects Gradle 9.1.0 in `gradle-wrapper.properties`. The wrapper JAR
and launch scripts have now been regenerated with that same version. The previous
JAR was the authentic Gradle 4.6 wrapper, despite the newer distribution selected
in the properties file. Older wrappers can launch newer Gradle distributions;
this mismatch alone did not establish a build failure or cause of Android runtime
bugs.

The existing distribution URL, SHA-256 pin, 10-second network timeout and URL
validation setting are unchanged. The refresh brings the wrapper implementation
and generated scripts into agreement with those settings. It does not change
Android Gradle Plugin, Kotlin, app dependencies, signing or licensing requirements.

## Provenance

Check these values against Gradle's [published release checksums](https://gradle.org/release-checksums/)
before executing a downloaded distribution or accepting a wrapper replacement.

| Artifact | SHA-256 |
| --- | --- |
| Gradle 9.1.0 binary distribution | `a17ddd85a26b6a7f5ddb71ff8b05fc5104c0202c6e64782429790c933686c806` |
| Gradle 9.1.0 wrapper JAR | `76805e32c009c0cf0dd5d206bddc9fb22ea42e84db904b764f3047de095493f3` |
| Previous Gradle 4.6 wrapper JAR | `381dff8aa434499aa93bc25572b049c8c586a67faff2c02f375e4f23e17e49de` |

The JAR is generated output, not a locally edited archive. `gradlew` retains its
executable bit. `gradlew.bat` uses the existing repository's LF line endings;
apart from line-ending normalization, both launch scripts are generated output.

## Reproduce without configuring the Android project

Use a separately downloaded and checksum-verified Gradle 9.1.0 binary
distribution. Generate the wrapper in an empty project, so this operation does
not require the private `:licensing` module, Android SDK or release signing key:

```sh
WRAPPER_SEED=$(mktemp -d)
printf '%s\n' 'rootProject.name = "wrapper-seed"' > "$WRAPPER_SEED/settings.gradle"
/path/to/verified/gradle-9.1.0/bin/gradle \
  --project-dir "$WRAPPER_SEED" \
  --gradle-user-home "$WRAPPER_SEED/gradle-user-home" \
  --no-daemon wrapper \
  --gradle-version 9.1.0 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum a17ddd85a26b6a7f5ddb71ff8b05fc5104c0202c6e64782429790c933686c806 \
  --network-timeout 10000 \
  --validate-url
sha256sum "$WRAPPER_SEED/gradle/wrapper/gradle-wrapper.jar"
```

Review the generated files before copying the JAR and scripts into the repository.
The generated properties have the same settings as the checked-in properties;
their key ordering need not be copied. Keep the checked-in distribution checksum
pin and script permissions intact.

Gradle documents that updating only `distributionUrl` does not refresh the JAR
and scripts. For future in-project upgrades, follow its
[wrapper upgrade procedure](https://docs.gradle.org/9.1.0/userguide/gradle_wrapper.html#sec:upgrading_wrapper),
including the second wrapper invocation that refreshes the generated files.

## Validation performed for this refresh

The following checks used the generated wrapper or the verified Gradle 9.1.0
distribution. Negative probes ran in disposable projects and did not alter this
repository's properties.

| Check | Observed result |
| --- | --- |
| Official distribution and generated JAR SHA-256 | Both match the published values above |
| `./gradlew --version` with a fresh isolated Gradle user home | Downloads and verifies the selected distribution; reports Gradle 9.1.0 on JDK 17 |
| Incorrect distribution checksum on a local test ZIP | Bootstrap exits nonzero with a checksum verification error |
| Local HTTP test server stalls with `networkTimeout=200` | Bootstrap exits nonzero with the configured 200 ms timeout in its diagnostic |
| `wrapper --validate-url` with a nonexistent local distribution URL | Generation exits nonzero with a distribution-URL validation error |
| `sh -n gradlew` and `git diff --check` | Pass |
| Properties and file modes | Properties remain byte-identical; Unix launcher remains executable |

`networkTimeout` bounds download network operations. `--validate-url` checks the
distribution URL when the wrapper task generates files; it is not a replacement
for distribution checksum verification. See Gradle's
[wrapper options and verification documentation](https://docs.gradle.org/9.1.0/userguide/gradle_wrapper.html).

These checks verify wrapper provenance and bootstrap behavior. They do not
configure or build the Android app, exercise the Windows launcher, verify any
WhatsApp hook, or replace Android CI and authorized device testing.
