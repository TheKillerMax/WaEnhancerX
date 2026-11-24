# Target identity and runtime evidence acceptance

The manager's active-module indicator, version-policy decision, stored initialization report and current process observation answer different questions. None certifies every feature.

## Current contract and upstream changes

This gate follows nightly HEAD `9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d` and its source contracts. Earlier expectations are preserved in review evidence, rather than silently treated as current requirements.

| Earlier expectation | Current production contract | Source of change |
| --- | --- | --- |
| 25-second heartbeat/observation expiry and a five-second Compose clock | Same boot, reported PID present in the live process observation and a positive report timestamp; refresh is on demand | `1b029ec88d9c4f7fbc88261f3bd2a9b16b16e342` removed RuntimeObservationClock and the age APIs |
| Custom version permission shown as unverified | A custom rule is an allowed version decision; ready/provider reports can be presented as complete | `d7fd3110eeff9b166042964d8036e7a25d47697e` explicitly changed this policy |
| Every installed target had to be running for a healthy summary | Closed targets retain their own unconfirmed card and do not downgrade another running, ready target | Current TargetRuntimePresentation.summarize and upstream target-lifecycle changes |
| Per-target pidof protocol with cache expiry | One shared root probe stages scope and returns a filtered ps listing bounded by begin/end markers | Current RootProbe in TargetAppManager.kt |
| Built-in permission for the old 2.26.39 branch | The declared array currently covers 2.26.40 through 2.26.46; old 2.26.39 examples are rejection checks | app/src/main/res/values/arrays.xml |

These are reconciliations of intentional upstream changes. The QA patch does not change production version permission, process evidence, target scope or presentation policy.

## Version and resource decisions

UniversalVersionValidator.evaluate preserves the distinct reasons for admission, explicit rejection and unavailable inputs. Missing module resources, foreign numeric resource IDs and unreadable preferences cannot supply a valid allowlist. Resource access never loads target application code. Built-in rules keep precedence over custom rules; an explicit existing bypass remains distinct and is presented as unverified.

VersionGuard pauses on rejection or unavailable evidence. Queued notices retain their decision-generation guard: an obsolete queued pause cannot render after a successful check or overwrite a newer failure. UI labels, reports and transport continue to expose the actual decision.

## Process observation, scope and refresh

InjectionEvidence requires an active module, known current boot, positive reported PID/timestamp, the same recorded boot, and that PID in the observed process set. Missing root output remains unknown; an observed empty set means stopped, and a different PID means changed. There is no retired wall-clock expiry API to emulate.

The actual process parser accepts modern and legacy ps layouts, skips malformed rows and service process names, deduplicates PIDs and publishes immutable maps/sets. Partial or incomplete snapshots do not turn unknown packages into known absence. RootProbe requires both output markers and a nonempty parsed listing; the manager's own process permits a valid observation of target absence. Observation time records the beginning of collection. Root denial, linkage failures and truncated output remain unavailable.

The process command filters exact declared package names plus the manager before the bounded root capture. Shell controls use a ps function fixture and the real local grep/shell; no real ps or su is executed.

The legacy CI filename test_runtime_observation_clock.py now tests the actual TargetAppManager refresh/drain bodies. It covers idle behavior, deferred scheduling, 1,000 batched requests, 100 requests made during an active probe, nonoverlap, failure recovery and causal lost-request controls. Its scheduler and probe IO are observable boundaries, with an explicit negative check that unconfigured probe IO fails closed. It does not recreate the removed clock.

## Executable gates and limits

- `python3 qa/test_runtime_diagnostics.py`: 201 current source/JVM assertions, six emitted-shell controls and actual UI/transport call-site guards. The unchanged production validator, VersionGuard, process parser, evidence and presentation classes are compiled with extracted production data/scope/probe bodies. Android types, root IO and presentation builders are explicit fixtures. Scope SQLite staging is outside this pure suite; an unconfigured scope boundary is rejected and root cannot run through it.
- `python3 qa/test_runtime_observation_clock.py`: actual on-demand refresh/drain behavior and two causal negative controls. The old filename stays as the existing workflow entry point.
- `python3 qa/verify_runtime_framework.py --out <new-directory> [--public-apk-cache <directory>]`: unchanged current public runtime utilities, including actual HookProviderIpc, compiled against real Android/Compose dependencies. The existing 12 Android 14 JUnit resource/localization cases and 22 debug/release resource contexts retain their original assertions and public APK SHA pins.
- `python3 qa/test_startup_reconciliation.py`: current startup hooks and on-demand reporting wiring.

The source fixture does not execute Compose rendering, Binder, Android root, HMA, Vector or LSPosed. The framework fixture validates public API compilation and resource decisions; it is not a full WAEX APK or host integration test. No private licensing source, signing material or host APK is required or claimed by these gates.

Device acceptance remains necessary for denied/recovered resource visibility, root timeouts, PID changes, app restarts, target scope, boot transitions, both official package variants, report requests and long-open UI refresh behavior. A healthy aggregate is a report of initialization under allowed version rules, not acceptance of every feature or every Android version.
