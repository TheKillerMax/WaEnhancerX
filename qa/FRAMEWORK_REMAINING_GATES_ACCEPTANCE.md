# Remaining framework gates

These runners exercise selected production source closures on Robolectric, with explicit external-service fixtures. They do not build or install WAEX, run WhatsApp or LSPosed, or certify ART/device/DSU behavior.

| Runner | Android SDKs | Required positive cases |
|---|---|---:|
| android_home_restart_test.py | 24, 28, 34 | 57 |
| android_work_profile_test.py | 24, 28, 34 | 87 |
| android_manager_layout_test.py | 28, 34 | 10 |
| android_media_preview_test.py | 24, 28, 34 | 60 |

## Compiler contract

kotlin_compiler.py preserves each compiler argument on Windows instead of sending semicolon-separated classpaths through kotlinc.bat. It uses the distribution's preloader and kotlin-compiler.jar, following that batch launcher's Java invocation. Other systems keep the distribution's executable.

Do not place every distribution JAR on the parent classpath: the bundled compose-compiler.jar can shadow the explicitly selected Compose plugin. The manager runner continues to require Kotlin 2.0.20 and the pinned non-embeddable Compose plugin 2.0.20. Version or metadata checks are not skipped.

The manager dependency fixture resolves the checkout's Android graph and Compose BOM using its Gradle metadata, rejects desktop artifacts, and records each resolved artifact hash. An already resolved flat directory and its sibling resolved-sha256.json can be reused with --deps.

## Production closure and boundaries

The home gate compiles the complete home hook, BaseFeature, preference bridge, HookProviderIpc, privacy model, WaJid and policies. Its restart, host discovery, contact lookup, menu and display endpoints remain explicit fixtures. The added contact/JID endpoints fail loudly, increment a counter and are asserted unused after every test, even when an exception could be swallowed by production.

The work-profile gate retains its 87 cases, real project-pinned OkHttp APIs and complete restart/update implementations. Context/profile metadata and privileged subprocess outcomes are controlled fixtures; no actual work profile or root command is exercised.

The manager gate measures the exact extracted dashboard and bottom-navigation expressions with real Compose and Android text. It is not a complete manager screen or accessibility assessment on a physical device.

The media gate and its 60-case contract require the restored PR90 lifecycle fixtures and the session-owned media product port. Publishing the launcher alone does not provide that product behavior.

## Evidence requirements

Use a fresh output directory for every attempt. Keep the generated sources, dependency and SDK hashes, JUnit output and result JSON. A positive requires the exact case count, zero failures and exit status zero. Infrastructure failures never count as negative behavioral controls.

The launcher hash is included in each runner receipt. Local validation used JDK 21.0.13.1 and Kotlin 2.0.20; this does not establish equivalent results for another compiler or source revision.
