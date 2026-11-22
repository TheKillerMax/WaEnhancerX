# Source/JVM Robolectric runtime dependency repository

Current upstream Source QA had multiple failures where Robolectric fetched its
actual pinned android-all-instrumented jars from Maven Central and received
HTTP 429. These failures occurred before the tests could execute. They must
remain FAIL/BLOCKED, not be accepted as passing tests.

This maintainer-only CI experiment sets WAEX_ROBOLECTRIC_RUNTIME_REPO to the
Google Cloud-hosted public mirror of Maven Central for Robolectric runtime
artifacts. Local runs default to the existing Maven Central URL. A strict
two-source allowlist rejects unreviewed URLs and credentials. The generated
Gradle probe receives this through testOptions.unitTests.all system properties.
All full Android/JVM QA suites and the native WAEX sources retain their
original dependencies, tests, expected results and failure behavior.

References:
- https://robolectric.org/configuring/ (documented system property)
- https://docs.cloud.google.com/docs/buildpacks/java (documented mirror URL)
- https://maven-central.storage.googleapis.com/index.html (unofficial support status)

Artifact identity observations on 2026-11-22:
- android-all-instrumented:14-robolectric-10818077-i7.jar SHA-1
  dd5e1d356107e9d99ebf58beb5329debe2849140
- android-all-instrumented:9-robolectric-4913185-2-i7.jar SHA-1
  62774277200aae1785bba84232aec389dc7a0953

The SHA-1 published beside each artifact matched byte-for-byte between
Maven Central and the GCS mirror. This is metadata equivalence, NOT
an independently downloaded and byte-hashed JAR or runtime pass.
SHA-1 is used here only as an existing artifact publication checksum;
stronger byte-level evidence is recommended before any release.

This changes a protected GitHub Actions workflow and introduces a public
external mirror. It therefore requires maintainer review under R5 and the
project's R6 network destination policy; do not auto-merge or weaken the gate.
A CI run on this exact branch must prove the runtime JAR fetch and the tests.
Even when fixed, product behavior in WhatsApp is NOT_VERIFIED.
