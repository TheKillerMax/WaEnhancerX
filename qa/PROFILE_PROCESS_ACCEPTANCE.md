# Profile-scoped process evidence

Reconciles the read-only process evidence subset of #98 against nightly
c089458569564c241e6e2cddbd5a4de301299f28. Preserve the existing event-driven
TargetAppManager and RootProbe architecture. No new root capability is added.
PackageManager's exact UID and the initiating manager PID must support an
observation; failed or incomplete process output remains unknown.

Run qa/test_profile_process_probe.py with a complete Kotlin distribution,
JDK21, pinned public Robolectric dependencies and --sdk-jars, using --mutations
for the 22-method API24/28/34 matrix and four causal fault classes.
The existing test_runtime_diagnostics.py entrypoint retains current
event-driven source guards and tests the exact emitted command using a shell
function that shadows ps. No real process enumeration, root execution,
LSPosed database, private engine, injection, or device acceptance is claimed.

The previous C03 evidence is historical, not a fresh certification. The
reconciliation does not include the remaining #98 IPC, preference sync,
root configuration or protected workflow changes. The current common diagnostic runner also executes the C04 screen-refresh
projections and eight causal refresh mutations. The separate observation-clock
suite continues to verify its own state and queue contracts.
