#!/usr/bin/env python3
"""Source-level contract assertions for startup isolation after the upstream merge.

Does not build Android, verify reflection contracts, or test LSPosed runtime.
The test guards existing upstream diagnostics and feature registration when
resolving the old startup PR onto a newer MainHook implementation.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app/src/main/java/com/waenhancer/xposed"
main = (SRC / "MainHook.java").read_text(encoding="utf-8")
guard = (SRC / "core/VersionGuard.kt").read_text(encoding="utf-8")
registry = (SRC / "core/FeatureRegistry.java").read_text(encoding="utf-8")

checks = {
    "one initialization attempt per process": "TARGET_INITIALIZED.compareAndSet(false, true)" in main,
    "startup preference preload retained": "sPreferenceBridge = new PreferenceBridgeClient(" in main,
    "initial provider sync before hook decisions": "resolvedBridge.awaitInitialSync();" in main,
    "hooked-package report retained": "WhatsAppPackageDetector.registerHookedPackage(" in main,
    "hooked-package report failures isolated": "Hooked-package reporting failed:" in main,
    "ActivityTracker retained": "ActivityTracker.install(" in main,
    "ActivityTracker startup failures isolated": "ActivityTracker initialization failed:" in main,
    "request update check retained": '"request_update_check", packageName, null' in main,
    "signed restart receiver retained": "appContext.registerReceiver(receiver, filter, RESTART_PERMISSION" in main,
    "exact restart package match retained": "packageName.equals(pkg)" in main,
    "live preference refresh receiver retained": 'com.waenhancer.action.PREFERENCES_CHANGED' in main,
    "restart prompt retained": "RestartPromptController.initialize(bridgeClient);" in main,
    "restart prompt failure isolated": "Restart prompt setup failed:" in main,
    "update sheet retained": "WhatsAppUpdateSheet.init(" in main,
    "update sheet failure isolated": "WhatsApp update-sheet setup failed:" in main,
    "injection toast retained": "Injecting WAEX hooks into WhatsApp..." in main,
    "injection toast failures isolated": "Injection toast unavailable:" in main,
    "registry installed after optional UI hooks": main.index("WhatsAppUpdateSheet.init(")
         < main.index("FeatureRegistry registry = "),
    "hook initialization preserved": "registry.initializeAll();" in main,
    "hook diagnostics preserved": "registry.reportInjectedHooks(appContext, packageName);" in main,
    "detailed injection error sheet preserved": "showInjectionErrorSheet(t, packageName, lpparam.processName);" in main,
    "source-level verified version check": "VersionGuard.verifyAndGuard(" in main,
    "version detection still supported": "UniversalVersionValidator.isSupported(appContext, currentVersion, prefs)" in guard,
    "version check fails closed": "return false // Fail closed: unknown obfuscated methods must not be hooked." in guard,
    "version check does not fail open": "return true // Fallback to allowing execution" not in guard,
    "warning retry after UI creation failure": "A failed UI attempt must not permanently suppress future warnings" in guard,
    "new factory-based feature registry": "private interface FeatureFactory" in registry,
    "new registered features preserved": "MessageDeviceSourceHook.class" in registry
         and "FilterItemsHook.class" in registry,
    "per-feature installation protection": "entry.feature = entry.factory.create();" in registry
         and "entry.feature.hook();" in registry
         and 'entry.status = "FAILED";' in registry,
}
for label, passed in checks.items():
    if not passed:
        raise AssertionError("Startup reconciliation regression: " + label)

# Every optional setup that occurs before feature initialization must have
# its own failure-handler context. Checking the nearest meaningful surrounding
# source is static evidence only, not proof of runtime exception isolation.
for operation, warning in [
    ("ActivityTracker.install(", "ActivityTracker initialization failed:"),
    ("WhatsAppPackageDetector.registerHookedPackage(", "Hooked-package reporting failed:"),
    ("RestartPromptController.initialize(", "Restart prompt setup failed:"),
    ("WhatsAppUpdateSheet.init(", "WhatsApp update-sheet setup failed:"),
    ("Injecting WAEX hooks into WhatsApp...", "Injection toast unavailable:"),
]:
    before = main.index(operation)
    after = main.index(warning)
    assert 0 < after - before < 1000, f"No nearby failure handler for {operation}"

print(f"PASS: {len(checks)} startup/version-guard/registry source invariants")
