# Call-menu host ownership contract

This focus adds only CallTypeHostContract and public offline fixtures. It does
not register a call selector, alter host operations, or enable a preference.
The dependent selector focus supplies the UI and its complete regression suite.

## Source contract

Discovery requires a unique contact-menu owner, a unique popup dispatcher and
exact agreement on two instance void(boolean, boolean, boolean) interface
operations. The classic menu must open the popup belonging to the same owner.
A concrete Conversation Activity and one typed View adapter owned by the
Conversation Fragment must implement those operations. All four concrete sites
must resolve. No menu number or obfuscated member name selects a recipient.

Reflection requires the typed getChatJid/getRawString relation and a unique
lifecycle state getter with exactly the five AndroidX state names. Every live
snapshot checks the exact owner type, RESUMED state, attached Activity window,
adapter visibility/attachment and the Fragment's authoritative adapter field.
Unsupported or ambiguous shapes fail closed. PN and LID namespaces stay distinct.

The contract implementation is byte-for-byte the public #91 source. This
reconciliation does not guess a new host binding from the installed version.

## Reproducible offline suite

Supply the repository's verified public framework dependency graph, its three
instrumented Android SDK JARs and the pinned DexKit 2.2.0 API JAR:

    python3 qa/android_call_type_test.py --suite contract --out /tmp/call-contract \
      --deps /path/to/bundle/deps --sdk-jars /path/to/bundle/sdk-jars \
      --dexkit /path/to/dexkit-2.2.0.jar

The runner starts no network acquisition and makes Robolectric offline explicit.
Eight test methods run on API 24/28/34: exact four-site resolution, live PN/LID
reading, unknown-peer rejection, resumed-owner checks, ambiguous adapter
rejection, mixed-interface rejection, native-operation rejection and ambiguous
lifecycle rejection. JUnit records assertion failures separately from setup,
linkage, compilation and environment errors. All 24 cases must run without skips.

Complete public DexSearchEngine/DexCacheManager and the pinned DexKit API compile;
native DexKit matching is not simulated as success. Android Activity/View APIs
are real Robolectric framework classes; host shapes and Xposed are explicit
fixtures. Generated BuildConfig follows the checked current Gradle version
contract. MainHook contributes only its checked public module-path descriptor.

## Evidence boundary and dependencies

Historical #91 evidence describes WhatsApp 2.26.40.76, input APK SHA-256
593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4.
That finding is not a compatibility claim for WhatsApp 2.26.46.x. Current-host
native binding and legitimate device acceptance remain unverified.

The host-contract focus can be reviewed/tested independently. The selector focus
depends on it; the protected workflow focus also depends on the current portable
framework-input producer. Local pass results do not replace R13 at a final SHA.
