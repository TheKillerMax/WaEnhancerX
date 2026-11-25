# Verified inputs for the preserved-message producer

The SourceQA producer consumes the same locked 36 framework JARs and three
Robolectric SDKs as Appearance. Both cache paths and keys are identical, so a
successful seed or an earlier consumer can supply the next run. Cache entries
are rehashed before the Android gate. A missing entry uses the existing bounded
transport and exact lock URLs; changed bytes stop preparation without a network
fallback. The producer no longer resolves the Maven dependency plugin.

The runner and its fixture remain unchanged. Their current denominator is 105:
35 cases on each of API 24, 28 and 34. The previous workflow label said 84; the
label is corrected without adding, removing or weakening any test. The public
DexKit input keeps the runner's existing bounded download and integrity checks.
Its `--deps` and `--sdk-jars` options bypass dependency resolution and select the
offline Robolectric SDK directory.

Framework and SDK receipts are recorded before the gate and rehashed offline
after the attempted gate whenever preparation succeeded. Reports are outside
the shared cache directories. A failed preparation cannot proceed to cache
publication or the Android gate. The original 20 bundle-transfer controls remain
unchanged.

The bundle creator also remains unchanged. It expects SDK paths in Maven's
directory layout. A small workflow adapter checks the three flat SDK files and
creates hardlinks under a new private directory in `RUNNER_TEMP`, using each
`maven_path` from the lock. This only adapts paths; it neither invokes Maven nor
reads the user's Maven repository. The adapter rejects existing output paths,
overlap with SDK inputs, wrong identities and any extra SDK entry before creating
the view. Its receipt records the three identities and the layout conversion.

The bundle creator rechecks all 39 inputs, copies them into its new output,
verifies the result, and binds its manifest to the current run, attempt and head.
Consumers continue requiring that same origin. A historical cache source is
never represented as the producer of the new run's Android results.

The gate exercises the existing declared Xposed and external-service fixtures
with Robolectric. It does not claim a complete APK build, private licensing
execution, a physical-device test or a kernel Binder test. Other SourceQA jobs
and Appearance's workflow are unchanged.
