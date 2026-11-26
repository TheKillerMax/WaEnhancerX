# Current view-once setter contract

The current `WaMessage`/`PrivacyToggle` hook is preserved. `WaTargets` now requires
one SQL caller and one invoked getter/setter interface; it resolves that setter's
exact name on message implementations. An inherited implementation is admitted
only when its declaring owner is itself a message class implementing the same
state interface. A generic superclass outside that interface or a default
interface implementation is rejected, avoiding a hook on a shared broad owner.
Unrelated `(int)void` members, foreign classes, ambiguous interfaces and invalid
cached methods cannot authorize a hook. The existing string anchor is unchanged.
Cache generation v3 stores the exact interface setter as a header and validates
every concrete member against its name and owner; the header is never hooked.
Constructors are skipped before DexKit reflection conversion. Genuine unresolved
method candidates and multiple SQL callers remain unavailable.

`test_view_once_setters.py` compiles complete `WaTargets`, `WaMessage`, `WaJid`,
`HookErrors` and the new helper against pinned DexKit2.2 and Android API classes.
The 38 executable checks pass; five independently compiled mutations fail
6, 1, 2, 2 and 4 assertions. DEX scanning and cache transport are controlled
boundaries. Contact lookups fail if unexpectedly invoked.

The exact DexKit2.2.0 source at `ffa6c51c38fe3ecfddb18d8949c30c48dbfbfd6a`
includes invoke-direct constructors in `MethodData.getInvokes`; its
`InstanceUtil.getMethodInstance` rejects non-method descriptors. This is the basis
for the explicit `isMethod()` guard. The fixture does not execute a real DEX query.
Static-cache checks remain; removing that flag alone is redundant with Java's
interface-owner contract. Native implementations of the correct interface/name
exercise the independent native-method gate instead.

Example: `python3 qa/test_view_once_setters.py --out /tmp/waex-viewonce --android-api /path/android-all-14-robolectric-10818077.jar --dexkit-jar /path/dexkit-2.2.0.jar --mutations`.
Set `KOTLIN_HOME` to the Kotlin2.0.20 installation and use JDK17 or later.

This is no evidence that any new WhatsApp version contains the required DEX
contract, nor a device/LSPosed result. No version fingerprint or private licensing
policy changes. Exact-commit public CI and maintainer review remain separate gates.
