# Overlay settings recovery

This focused change carries the overlay settings portion of PR #108 onto nightly
`c089458569564c241e6e2cddbd5a4de301299f28`, retaining its current onboarding and UI.
It does not carry the floating bar, channel visibility or host view selector changes.

The launcher tries the package-scoped overlay settings action first. If Android
throws ActivityNotFoundException or SecurityException, it tries package-scoped
App info. It reports false only when those expected unavailability conditions
prevent opening either screen. Unrelated lifecycle/programming errors propagate.
The screen displays recovery guidance and an App info action while the requested
overlay permission remains ungranted. Permission is still optional; Android and
the user decide whether to grant it.

## Verification

Run with a complete JDK 17 or later and the public Robolectric 4.17 dependency
cache plus instrumented API 24, 28 and 34 SDK JARs used by the framework suites:

```sh
python3 qa/test_overlay_settings.py --out /tmp/waex-overlay \
  --deps /path/to/framework/deps --sdk-jars /path/to/sdk-jars
```

The 2026-11-26 local run compiled the actual production Java helper and passed
seven behavior cases on all three APIs, for 21 JUnit executions. Cases cover the
package and action, both expected launch failures, an unavailable fallback,
explicit App info, propagation of unrelated exceptions, and unchanged Android
overlay authorization after opening settings. XML keys were checked in English,
Spanish, Latin American Spanish and Slovenian. Source and dependency hashes are
recorded by the runner.

Two separate production mutations also compiled and completed all 21 executions:
removing the fallback produced nine assertion failures in the three fallback
cases, and swallowing unrelated RuntimeException produced three assertion
failures in the exception propagation case. Setup failures were not counted.

The Java suite uses actual Robolectric Intent and Settings classes. It does not
compile Compose, build or install an APK, interact with OEM Settings, grant a
permission or establish coverage for every Android release. Public CI on the
published commit and UI/device acceptance remain separate gates.
