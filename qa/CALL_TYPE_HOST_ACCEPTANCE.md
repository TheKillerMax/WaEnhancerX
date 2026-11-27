# Call-type host profiles and acceptance

C14 replaces the direct-invocation discovery assumption with two exact APK
profiles. This is a reviewable delta on C12 selector B, commit
`17db77b86670fec071f843154f26aef9d7dccd16`, tree
`6bf0471939097b3de99b28a34aae60e3b632ff73`. Neither published C12 parent is
changed. The complete A/B/C14 stack is larger than this focused delta and must
be assessed separately against nightly and R4.

## Inputs inspected

Only these package names and complete base-APK bytes are accepted:

| Package / inspected version | Bytes | SHA-256 |
| --- | ---: | --- |
| `com.whatsapp` / 2.26.46.82 | 90265021 | `bde176036af43fc9540d0cc76ad6162d2fcd4c9845f91d9c1603e84bb605bb83` |
| `com.whatsapp.w4b` / 2.26.46.83 | 105226514 | `bab1f720551c2e84dedabbb01d2f1a0a8947b12ab764f64c50db03af0992dc20` |

Version labels alone, other APK variants, modified bytes, renamed packages and
unknown identities do not enable this selector. Each new profile requires a
fresh code investigation; the map is not a compatibility range.

## Cause and static evidence

Neither current `onOptionsItemSelected(MenuItem)` nor the anchored popup
dispatcher directly invokes the outgoing boolean pair. Both dispatch generated
Runnables through a gate that may defer execution. The old direct `getInvokes()`
predicate therefore finds zero outgoing operations in both entry points.

| Input | Classic Runnable cases | Popup Runnable case | Shared interface operations | Concrete adapter |
| --- | --- | --- | --- | --- |
| Personal | `X.MaS.run`, 23 / 24 | `X.MYe.run`, 8 | `X.0p1.C70(ZZZ)V`, `C73(ZZZ)V` | `X.60R` |
| Business | `X.Xgj.run`, 35 / 36 | `X.Xgt.run`, 14 | `X.0oi.CMV(ZZZZ)V`, `CMY(ZZZZ)V` | `X.8Zt` |

The classic captures refer to the selected menu and its current conversation
API; the popup captures refer to the corresponding holder and the same API.
The last argument is false in the classic branches and true in the popup
branches. Personal forwards the preceding two menu/gate flags. Business
forwards three preceding flags, including its additional menu flag, without
dropping, reordering or synthesizing any value. Both `Conversation` and the
listed View adapter declare the operations. This is not an inherited-method
lookup failure, so changing `getDeclaredMethod` to `getMethod` is insufficient.

Evidence retained in the C14 call-binding review includes DEX code-unit offsets,
register operands, constructor captures, switch targets, normal branch flow and
exception tables. The selected Runnable branches have no overlapping handlers.
APK SHA-256 is checked before and after each bounded static query. No target
class or method was executed. DexKit 2.2.0's public MethodData API does not expose
the register operands and switch targets needed to prove this branch association;
a union of multipurpose Runnable invocations would weaken the original contract.

## Contract retained

The profile only selects code entry points. A receiver's current typed
`getChatJid()` remains the recipient source. Both outgoing methods must belong
to the same interface, have equal arity of exactly three or four primitive
booleans, and resolve to four concrete declared operations on the inspected
Activity and adapter. Native, abstract, static, synthetic, ambiguous and mixed
contracts remain rejected. No recipient is obtained from a profile or menu ID.

The live owner must remain resumed and attached. A fragment adapter must still
be the authoritative instance in its host Fragment's unique adapter field.
PN/LID separation, authoritative LID mapping, current-peer checks, cancellation,
screen disposal and exact single original continuation are unchanged. All
arguments are cloned when the selector takes ownership. Phone opens ACTION_DIAL.

The existing registry predicate is the restart-tracked `call_type_controller`
preference, not `PrivacyPrefs.isAvailable`. Off at startup is DISABLED and does
not fingerprint or install hooks. Failed partial registrations stay inert even
when unhook fails; a new registry instance can retry without reviving the old
callbacks. Registry, MainHook and the two published parents are not modified.

## Reproduction without downloads or device actions

The existing offline runner checks 150 Android fixture executions: 36 contract
and 114 selector cases at API 24/28/34. The original C12 code, with the expanded
contract fixtures, fails only the four-argument positive in the three SDKs
(36 cases, 3 expected failures). Fixtures do not prove live host binding.

    python3 qa/android_call_type_test.py --suite all --out /tmp/call-selector \
      --deps /verified/deps --sdk-jars /verified/sdk-jars \
      --dexkit /verified/dexkit-2.2.0.jar

To additionally run the production fingerprint over already-owned APK files,
supply both optional inputs explicitly. Neither path is downloaded or installed.

    python3 qa/android_call_type_test.py --suite all --out /tmp/call-selector-apks \
      --deps /verified/deps --sdk-jars /verified/sdk-jars \
      --dexkit /verified/dexkit-2.2.0.jar \
      --personal-apk /owned/personal-base.apk --business-apk /owned/business-base.apk

`CallTypeProfileFileCheck` performs 15 file checks, including both exact profiles,
cross-package rejection, a same-size copy with one changed byte, missing inputs
and metadata-triggered revalidation. The helper changes only its own temporary
copy; the runner verifies that both supplied inputs remain unchanged. Without
APK inputs the result explicitly records `profile_file_check: NOT_REQUESTED`.
Those file checks supplement the 150 fixtures; they are not Android runtime tests.

## Performance and remaining gates

The fingerprint follows the existing MediaHostFingerprint strategy: a 64 KiB
streaming buffer, expected byte bound, before/after metadata checks and a
process-local memo keyed by expected profile, canonical path, size and mtime.
An unchanged accepted or rejected input is not rehashed at each bind. The
fingerprint is consulted during installation, never in a call interception.

Initial Windows/JDK measurements on the actual files were 172.10 ms Personal
and 173.27 ms Business; 100 memoized lookups took 14.16 / 13.92 ms total.
These are first lookups in that Java process with an already-used OS file cache,
not Android cold-storage timings. MainHook installs startup features on the main
thread and lazy installs may also run from Activity callbacks. Cold Android/UI
latency remains a material acceptance gate. No like-for-like native DexKit
timing was measured, so this change is not claimed as a performance improvement.

Runtime reflection against the installed host ClassLoader, AndroidX fragment
behavior, LSPosed injection, real navigation/cancellation, resource resolution,
full-module build, device behavior and hosted R13 at a final reviewed SHA remain
separate gates. Offline success does not authorize or demonstrate a real call,
APK installation, merge or integration. Unknown identities retain host behavior.
