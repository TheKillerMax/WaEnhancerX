# Profile identity and bounded runtime reporting

## Source and integration basis

This continuation ports the applicable public contracts from PR98 head
`eb84075516b430d6ed3abdd903fde36c31808263` onto integration head
`8ec75da234b5ab6d0b643c25920a941e1f164b8f`. The integration already includes the
current on-demand refresh architecture, HMA caller/configuration repair, ClassValue
caches, edit-history preservation and the completed framework/media changes.

The legacy head is a behavioral reference. It is not copied over newer product
classes. In particular, periodic heartbeat polling, cache expiry and obsolete
custom-version presentation policy are not reintroduced. Missing or failed new
observations remain unknown in the current on-demand state model.

The existing HMA `source-qa.yml` is preserved byte for byte as the prefix of the
workflow; the runtime reporting checks are a separate job. All modifications are
public source or QA. No private implementation or licensing substitute is added.

## Production contracts

### Profile and process identity

The manager Context must identify `com.waenhancer`; its full UID must match
`Process.myUid()`. The shared `AndroidUserScope` helper also rejects invalid UIDs
and a Context from another Android user. PackageManager metadata must identify
the requested package and the same user. The manager package metadata must match
the current process UID. An uninstalled target is omitted from the query and
remains unknown; it is not recorded as a stopped process.

The single shared root probe emits `pidof` checks for installed targets and the
manager. Shell pathname expansion is disabled. The exit status and PID syntax
must agree, and each PID's four kernel UID fields must be numeric and equal.
Only the expected full UID is included. Missing status data, malformed values or
an unsuccessful command invalidate the probe. A foreign user's PID cannot be
reported as a target process in the manager's profile.

The parser requires exactly one valid UID-qualified row per queried package.
Duplicate or unexpected rows, incomplete output and nonpositive/invalid PIDs do
not establish process presence or absence. Root output must have exact, unique
begin/end markers, with the end marker last. The manager row must contain the
current manager PID. Observation time is captured before the command. Published
maps and PID sets are immutable. An explicitly queried empty PID set means a
successful observation of no process; unqueried or unavailable evidence stays
unknown. PID observation alone does not establish successful hook initialization.

### Bounded optional reporting

`RuntimeReportDispatcher` has one worker and at most one pending task per kind:
package registration, runtime health, hook inventory and update check. Replacing
a pending kind moves it to the newest chronological position. A delayed READY
report cannot overtake an already queued inventory report. Report timestamps are
captured with the observation, before queue delay.

MainHook preserves the current deferred release on the first visible Activity
or its bounded fallback. Before release the queue is already bounded. Repeated
release is harmless. The worker is a daemon with minimum Java thread priority.
MainHook passes that same dispatcher to FeatureRegistry. The registry captures
the inventory on the caller and enqueues the actual provider call on the shared
worker. An additional asynchronous queue cannot let READY overtake its inventory
delivery. The original three-argument registry constructor remains available and
uses a bounded default dispatcher. Each queued inventory is a captured JSON
snapshot; an IPC stall cannot accumulate one task per update.

Optional transport failure does not stop successful feature initialization.
Fatal VM errors retain their propagation contract. The authoritative initial
preference read still precedes version checks and feature initialization. An
interrupted startup waiter restores its interrupt flag and aborts initialization;
it does not cancel the independent provider read. Completed read failure keeps
the established disk fallback. Live preference changes request an asynchronous
refresh through the existing ordered bridge worker.

### Telemetry and configuration notifications

`PreferenceSyncPolicy` filters the explicit runtime observation keys before the
application's configuration listener performs restart tracking, preference
notifications or target broadcasts. Ordinary settings, operational switches,
entitlement configuration keys, unknown future keys and the null clear callback
retain their existing configuration notification path.

The three diagnostic provider routes notify runtime observers after successful
persistence; hook registration also notifies inventory observers. They do not
notify the generic configuration URI. Both registration routes return the actual
commit result. Caller UID/PID capture before identity clearing, caller scope,
full-UID package ownership, status validation and `finally` identity restoration
are retained. This change does not alter entitlement decisions or generic write
policy.

## Executable coverage and boundaries

| Gate | Executed acceptance | Source boundary |
| --- | --- | --- |
| `test_runtime_diagnostics.py` | 255 compatibility/evidence/presentation checks and 24 emitted shell controls | Complete public UID parser/helper and shared policies; explicit Android/root models and literal current RootProbe/model members |
| `test_runtime_report_queue.py` | 23 checks, including 300,000 replaced tasks | Complete production dispatcher; controlled executor/blocked task endpoints |
| `test_startup_hook_reporting.py` | 14 scenarios and 246 checks, including 1,000 updates behind blocked IPC | Literal registry methods and actual queue field, complete dispatcher; explicit feature/JSON/IPC boundaries |
| `test_injection_io_runtime.py` | 15 scenarios | Literal public MainHook members and the actual registry constructor binding/report method; complete bridge, dispatcher, schema and HookErrors |
| `test_preference_sync_runtime.py` | 76 scenarios and 1,725 checks | Literal application listener and provider telemetry/authorization spans; complete public policy/store/tracker classes |
| `android_runtime_profile_test.py` | 36 framework cases: 12 each on API24/28/34; 26 current unit-consumer tests | Complete AndroidUserScope, declared-target policy, InjectionEvidence and UID helper; literal current RootProbe/model members |
| `test_runtime_observation_clock.py` | 11 current refresh/drain checks, 1,100 coalesced requests; 2 behavioral negatives | Actual current on-demand coordination methods with explicit scheduling/root boundary |
| `test_startup_reconciliation.py` | 39 source invariants | Current initialization, diagnostics and nonblocking refresh contracts |
| `test_bridge_contract.py` | Hydration, ordered async edits, snapshots, clear/remove, errors and listeners | Complete public bridge with declared provider/platform boundaries |
| `test_provider_derived_keys.py` | 34 generic preference/health/clear policy assertions and source wiring | Existing derived-evidence write protections; does not execute private provider services |

The affected complete bridge also passed the existing 57 home lifecycle and 60
media-preview framework executions on API24/28/34. The isolated Android/Compose
resource gate compiled the complete current public detector, scope reader, UID
helper and related runtime utilities, and passed 12 Android14 JUnit methods,
22 public-APK resource contexts and the current locale-table checks. Its public
APKs and Gradle dependencies were supplied from verified existing caches.

The profile suite uses Robolectric 4.17, JUnit 4.13.2 and Android-all
`14-robolectric-10818077`. Standard Robolectric shadows supply UID and package
metadata; the Application, Context, PackageManager and Process APIs are Android
framework implementations. A minimal resource-only APK is compiled with an
already installed AAPT2 and stable Android platform 34 or newer. Robolectric
4.17 requires this binary manifest to create the intended application package.
The fixture asserts the package identity before testing the product guards.
Tool, manifest and generated APK hashes are retained. No APK is installed.

Shell controls execute the product's emitted shell fragment with a controlled
`pidof` function. The three `/proc/$pid/status` path occurrences are replaced by
owned fixture status files; reversing that replacement must reconstruct the
original shell. Both primary/work-profile UID values, foreign UIDs, absence,
status failures, PID globbing and all four UID fields are covered. No actual
Android `su`, process enumeration or device `/proc` read occurs.

`runtime_source_slices.py` records the whole source SHA-256, exact UTF-8 byte
spans, fragment hashes, generated-source hash and exclusions for each extraction.
Product statements in these spans are copied literally. Imports and enclosing
test scaffolding are separate. This is not compilation of complete MainHook,
FeatureRegistry, HookProvider or WaexApp. Their unrelated private initialization,
hook installation and services are not supplied by fake implementations.

## Legacy oracle mapping

| Legacy expectation | Current treatment |
| --- | --- |
| Profile/UID agreement, strict records, explicit absence and unavailable output | Retained and strengthened with exact manager Context UID, metadata identity, current manager PID and frame checks |
| Invalidating the old inspector cache after failed/missing-package observations | Current RootProbe has no independent inspector cache; failed probes remain unknown and uninstalled targets remain unqueried |
| Periodic heartbeat callback must remain responsive | Retired callback is not restored; current on-demand hook-report receiver is checked under blocked delivery and repeated requests |
| Slow package/inventory/update I/O, initial synchronization, interruption, fallback, failure isolation and duplicate initialization | Retained in public literal-member execution; deferred-release responsiveness is added |
| Old attach callback timing | Current private attach/custom-props integration is excluded; the fixture explicitly attaches the real asynchronous bridge before invoking the public initializer |
| Notification fan-out, commit failures, full caller UIDs, metadata filtering and settings/clear refresh | Retained for all three changed diagnostic routes and the actual listener spans |
| Full generic provider writes and entitlement engine | Five unchanged legacy scenario families are explicitly excluded: generic valid write, generic disk-failure signal, privileged clear route, derived/schema route guards and entitlement enforcement |
| Public derived-key and caller policies | Existing complete public policy tests are retained and executed separately; they are not presented as whole-provider or private-license coverage |
| Old TTL/custom-version presentation expectations | Retired architecture expectations are not reinstated; current on-demand and version-policy oracles remain in the existing runtime suite |

The five excluded provider families appear by name in the runtime result JSON.
Configuration notifications for entitlement keys are tested as public strings;
this does not simulate or certify licensing decisions.

## Causal negative controls

The eight I/O controls reintroduce an independent catalogue queue, inline optional work, old pending order,
delivery-time timestamps, synchronous live refresh, skipped initial sync, lost
interrupt status and continued initialization after interruption. Each must
compile and fail its named runtime assertion.

The seven preference controls reintroduce listener feedback, provider feedback,
lost clear refresh, false success in each registration route, lost entitlement-key
notification and unscoped Binder caller trust. Each requires the intended
scenario's assertion failure.

The eight identity controls admit a foreign process UID, foreign package profile,
another Context UID in the same profile, missing package rows, shell globbing,
an unrelated manager PID, a timestamp taken after collection, or truncated output.
Each must reach `COMPILE_OK` and its named behavioral invariant. A compiler error,
setup failure, absent result or timeout cannot count as mutation rejection.

The current candidate rejected all 23 controls. The existing observation gate's
two request/drain negatives also remain green. The catalog gate retains three
source-guard negatives; these are distinguished from executed behavior checks.

The shared-worker check was added after composition review found that the old
registry transport double delivered synchronously while the current product
method enqueued a second asynchronous delivery. The final fixture executes the
literal registry report method and constructor binding, blocks its provider call,
and checks both READY ordering and worker identity. An isolated MainHook mutant
that selects the independent default dispatcher must fail those assertions.
Earlier I/O runs using the synchronous registry double are superseded for this
cross-component ordering claim.

## Reproduction

With a preinstalled JDK21, Python3.11+, Maven and Android SDK:

```sh
python3 qa/run_runtime_reporting_ci.py \
  --java-home "$JAVA_HOME" --out /tmp/waex-runtime-reporting
```

The CI runner uses the exact qualified nine-JAR Kotlin2.0.20 closure. Its helper
and lock are identical to the qualified class-metadata V4 helper (helper SHA-256
`67c31cb9b4ffb2f45f83aa7c4186ded17d804ae92c710c0206daa0c7b5600b23`, lock SHA-256
`22cbe8b32257e65cb65e1c894d7b5daa3c42d3a6fcfcaaf4c2207f36163b896d`).
The existing schema name in that receipt is preserved. No bundled compiler plugins,
wildcard distribution classpath, JDK download or license acceptance is introduced.
The compiler closure and JDK identities are rechecked after the gates.

Each Linux gate runs in its own process group. Timeouts and surviving descendants
are terminated before the log is closed and hashed; unexpected descendants after
a nominally successful gate are an infrastructure failure. The supervisor also
handles a descendant exiting between the group probe and kill operation. Its
normal, timeout, abandoned-child and exit-race controls were exercised separately.

For the standalone offline framework test:

```sh
python3 qa/android_runtime_profile_test.py \
  --android-sdk /path/to/existing/android-sdk \
  --deps /path/to/robolectric-jars \
  --sdk-jars /path/to/instrumented-sdk-jars \
  --out /path/to/new/profile-evidence
```

Existing instrumented SDK JARs are linked read-only on the same volume. Other
dependency and source inputs are hash-recorded. Outputs must use new directories.
The resource-table regression also accepts `--offline --public-apk-cache PATH`,
requiring the already pinned public APKs and an existing Gradle cache.

## Acceptance limits

These are host JVM, controlled shell and Robolectric results. They do not create
managed profiles, exercise Android kernel/Binder cross-user behavior, install
WhatsApp or a GSI, enter DSU, perform LSPosed injection, measure target startup
latency, or build the complete WAEX application. Blocked Binder I/O can still
delay its single report worker; bounded queues prevent unbounded pending work
but do not cancel the transaction. On-device behavior, private integrations and
full application release acceptance remain separate gates with their own evidence.
