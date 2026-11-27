# Incoming view-once identity and state contract

This change reconciles the incoming view-once part of proposal #106 with current
nightly. Media quality, frame rate and download behavior remain separate changes.

## Why this contract is needed

A message can contain more than one field of the key type. Selecting the first
field by reflection does not establish that it belongs to the current message.
The hook now resolves the unique immutable key read by the exact sender anchor.
Its immutable layout must contain one ID, one direction flag and one verified JID
subtype. Null keys, empty or missing IDs, missing chats and ambiguous layouts
preserve the original operation.

Discovery follows the state interface actually invoked by INSERT_VIEW_ONCE_SQL.
Only its exact concrete setter on verified message subclasses is eligible.
Unrelated (int)void methods are not targets. Multiple callers may agree on one
interface; conflicting interfaces remain unsupported. A standalone view_once
literal is not enough to identify this SQL state contract.

Callbacks ask the current PrivacyPrefs service on every event. Both current and
legacy keys, target scopes and existing root-key precedence are preserved.
Only an incoming message with state 1 changes to state 0. Outgoing messages and
other state values remain unchanged. An unresolved contract is reported even if
the toggle is currently off but available for live enabling. A registration
failure propagates a content-free error to FeatureRegistry, which discards that
instance and removes already retained hooks.

## Automated checks

The focused fixture compiles the complete AntiViewOnceHook,
ViewOnceMessageContract, PrivacyPrefs, PrivacyToggle and DndPreferencePolicy.
It executes 79 checks for each independently generated modern/legacy JID
namespace. Reflection and JVM execution are real; the Android service boundary,
DexKit metadata, BaseFeature registration facade and Xposed dispatch are explicit
doubles. The fixture does not run the complete FeatureRegistry or HookRegistrar.

Covered cases include incoming/outgoing/null/incomplete keys, inherited concrete
setters, unrelated receivers and integer methods, duplicate metadata, ambiguous
sender and SQL contracts, mutable/foreign key layouts, live preferences,
Personal/Business scope isolation, failed registrations and content-free errors.
There is no DexKit query from the callback path.

Five compiled mutations must complete all 79 assertions and fail behaviorally:
reversed ownership, ignored key ambiguity, unrelated setters, ignored preference
scope and incomplete keys. A compiler failure or an incomplete fixture run is
not an accepted mutation detection.

Run with JDK 17 or newer and Python 3:

    python qa/test_view_once_contracts.py --out /tmp/viewonce-modern --jid-family modern
    python qa/test_view_once_contracts.py --out /tmp/viewonce-legacy --jid-family legacy
    python qa/mutate_view_once_contracts.py --out /tmp/viewonce-mutants

Use a new evidence directory every time. Optional --dexkit-jar and
--kotlin-stdlib arguments separately compile the same production files against
the unmodified public DexKit/Kotlin APIs. The scripts never download dependencies.
Each receipt identifies the production source hashes and the fixture inputs.

## Host evidence and remaining acceptance

Static DEX inspection of WhatsApp Personal 2.26.46.82 and Business 2.26.46.83 found
one sender anchor and one SQL anchor per APK. In each, the sender reads a unique
immutable primary key despite another mutable field of the same key type.
The SQL interface has one getter/setter pair, with four concrete message
implementations whose getter and setter access the same state field.
This is static evidence, not a runtime DexKit query or message-instance witness.

Before claiming installed behavior, identify the official module artifact and
host APK hashes, verify actual callback registration and the primary message
instance, then exercise incoming and outgoing media independently. Verify
disabled and live-toggle behavior, restart, unsupported/ambiguous layouts and
diagnostic reporting. Do not use synthetic fixtures as a substitute for those
checks. No complete APK, real media transfer, universal host compatibility or
hosted R13 result is established by this standalone suite.
