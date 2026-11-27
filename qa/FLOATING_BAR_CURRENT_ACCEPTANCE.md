# Floating-bar lifecycle: focused current-nightly reconciliation

This subset of #108 preserves the current public hook, layout, host resource
lookup, styles and ScreenScopedFeature call sites. Production change matches
the historical C03 reconciliation. Only floating-bar behavior is in scope.
Meta AI/channel visibility and overlay permissions are not changed here.

Run qa/test_floating_bar_current.py with JDK 21, Kotlin 2.0.20, the exact
Robolectric dependencies and three instrumented SDKs, pinned DexKit 2.2 and
Core 1.18 APIs, and --mutations. The runner stages complete production files;
the Xposed transport, private interface declaration and host discovery remain
explicit fixtures. A healthy run has 12 methods across API 24/28/34 (36 cases).
Four compiled faults require their causal assertion on all three SDKs.

No WhatsApp DEX lookup, private engine, APK installation, physical GPU rendering,
frame-time, battery or device compatibility is claimed.
