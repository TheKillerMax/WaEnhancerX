# Spanish (Latin America) public UI localization — acceptance

## Source contract

Reviewed upstream: `d8b7d98a32ec2b85ecb40ccfff8d2c7bb79dff4d`.
The original English resources, other existing language files, preference schema,
asset catalog, licensing dependency and signing/build configuration are unchanged.
Spanish is explicitly `es-419` (`values-b+es+419`), with matching `values-es`
fallback. Legacy stored `es` is interpreted as `es-419` without rewriting settings.
Known status/build/category strings are localized only at display boundaries;
protocol strings, preference keys, IDs, user text and arbitrary server responses
are not run through a blanket text replacement.

## Repeatable checks

```sh
python3 qa/test_es419_localization.py
python3 qa/test_es419_runtime.py
python3 qa/mutate_es419.py --out /tmp/waex-es419-mutations
python3 qa/verify_es419_resources.py --aapt2 /path/to/aapt2 --out /tmp/waex-es419-resources
```

The first test verifies source/resource contracts. The second compiles the whole
production locale policies, resource helper, display label mappings and Kotlin
LocaleHelper with explicitly limited Android/Resources/Context substitutes. It
executes Java formatting, not Android resource selection or complete Compose
screens. Four unsafe source variants must compile and fail the targeted behavior.
The AAPT2 runner actually compiles all public resources, then links an isolated
strings/plurals fixture. Its APK is NOT a WAEX application, optimized Release,
installation test or device acceptance. It requires an actual AAPT2 executable.

## Authorized final artifact and device acceptance

Build Debug and optimized Release with the authorized private module and original
signing configuration. Inspect the final resource tables, not just source XML or
the isolated fixture. Verify all public strings and the recording plural remain
in default, es and es-419 configurations. Keep optimization enabled. The explicit
localized-UI resource keep file supplements the existing catalog/icon rules.

Exercise initial install, a saved `es` selection, explicit `es-419`, and System
with es-CL/es-MX/es-AR/es-CO/es-PE/es-US. Verify returning to English and other
supported languages; do not change their stored codes or existing translations.
Confirm the current in-app picker behavior. No new Android platform localeConfig
or AppCompat migration is included.

Review narrow and wide devices, portrait/landscape, large text, TalkBack labels,
right-to-left language switching, dialogs, input validation, zero/one/many counts,
long error messages, offline states, notification channels and all menu variants.
Verify that a language change/recreation does not require resetting preferences.
The controls are not widened or rearranged by this contribution: longer Spanish
labels can still reveal pre-existing clipping and need visual acceptance.

Verify app-owned text inside official WhatsApp and Business on exact supported
builds. Read module IDs only through a context owned by `com.waenhancer`; never
use those IDs against the host resource table. Test module visibility loss and
recovery. Unavailable module resources use explicit English source fallbacks to
avoid crashing the host; this failure path is not advertised as English-free.
The display helper must not change the host's process-wide default locale.

Compare stable keys and behavior of theme options, restart targets, typed editors,
privacy settings, scope, provider authorization and cryptographic labels. This
patch localizes presentation, not those settings' values or permission decisions.

## Boundaries

Private-module screens, server/user content, downloaded release-note bodies,
unknown plug-in labels, Android/PackageInstaller messages and technical error
payloads are outside this public source translation. Keep diagnostic details
verbatim when copied for debugging. Translating a toast does not fix its receipt
classification; translating a feature name does not prove that hook works.

Reconcile overlapping presentation edits from open receipt, presence, runtime,
updater and media-export PRs rather than replacing their entire files. This branch
is based on upstream main and does not silently absorb those other contributions.
No full app build, optimized final artifact, screenshot/device review, Binder,
LSPosed execution or all-feature certification was performed here.
