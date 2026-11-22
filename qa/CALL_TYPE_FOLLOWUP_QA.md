# Compiled call-type feature acceptance (separate, dependent QA proposal)

This focused suite is the unchanged 29-method x 3-SDK Robolectric 4.17
regression harness from the original large PR #91, split without reducing
the original expected 87 JUnit executions. The real production hook and host
contract are NOT included here. Apply after the independent call-type feature
branch has been merged into nightly, so all tests compile against the real
production source. Do not present this stand-alone QA proposal as a passing
run before the production dependency is available.

Reproduction with Java 21, Kotlin, Maven, Android dependencies and a verified
DexKit 2.2.0 API:

    python3 qa/android_call_type_test.py --out /tmp/waex-call-type-contract

The runner compiles the original CallTypeControllerHook, CallTypeHostContract,
DexSearchEngine, contact mapper and explicit Xposed fixtures; executes JUnit
on Robolectric SDK 24/28/34 and demands exactly 87 passing executions.
The actual APK, WhatsApp, native DexKit scan, phone calls and installed
Android device are outside this test. The public CI may also be blocked
by Maven Central HTTP 429 until maintainers address transport reliability.
