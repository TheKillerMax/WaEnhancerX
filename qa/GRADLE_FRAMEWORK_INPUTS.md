# Shared native runtime and Android SDK inputs

Stability and Interface Scale can consume the same verified 39-file framework
bundle as Runtime. Pass all four arguments together:

```
--framework-bundle DIRECTORY --bundle-run-id RUN_ID \
--bundle-run-attempt ATTEMPT --bundle-head-sha FULL_COMMIT_SHA
```

The bundle must belong to the current CI run, attempt and source commit. All 36
JARs and all three Android SDK JARs are checked before and after the suite. This
does not make those 36 JARs the Gradle project's dependency graph: only
`org.robolectric:nativeruntime-dist-compat:1.0.19` uses the exclusive local Maven
repository, with the unchanged original POM and locked JAR. Other Gradle
dependencies retain their existing metadata and repositories. The verified
Android SDKs 24, 28 and 34 are resolved offline. A different `--sdk` cannot be
combined with this closed bundle.

`--offline` separately requires the existing Gradle dependency cache; it is useful
for host qualification and does not enable a network fallback. Omitting the
bundle preserves the previous resolution path.

The helper validates each explicit consumer, project name and executing runner.
Stability identifies `qa/verify_stability_framework.py`; Interface Scale identifies
`qa/verify_interface_scale_framework.py`. Their input receipts use
`WAEX_GRADLE_FRAMEWORK_INPUTS_V1` and record those fields. Runtime retains its
existing defaults and `WAEX_RUNTIME_FRAMEWORK_INPUTS_V1` receipt. Dependency and
POM pins, test oracles, production sources and SDK selectors are unchanged.

Before any Test task executes, the Gradle callback verifies both the selected
module artifact and the actual Test classpath entry by size and SHA-256. A cache
copy at another path is allowed only when its bytes agree. The final input
receipt is written only after the original suite passes and the JAR files and
bundle are checked again. Evidence retains the actual callback, local repository
settings, origin and source hashes. These host framework tests do not claim an
APK installation, ART execution, DSU compatibility or a physical-device result.
