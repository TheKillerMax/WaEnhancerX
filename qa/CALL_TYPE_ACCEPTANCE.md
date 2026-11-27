# Phone-or-WhatsApp selector acceptance

This focus connects the existing public BOOLEAN call_type_controller setting
to a selector after the host has chosen its native voice/video operation. It
depends on the independently reviewed CallTypeHostContract focus. The registry
retains its current conditional registration and lifecycle policy.

## Behavior preserved from #91

- Off at startup means no host discovery and no installed selector callbacks.
- Both native voice/video operations preserve their original receiver and all
  three or four boolean arguments from the inspected profile. Choosing WhatsApp
  continues the exact original once.
- Phone opens only ACTION_DIAL. The dialer requires the user's confirmation.
  Dialer failure keeps WhatsApp/cancel available and never makes an automatic call.
- Cancel, back, dismissal, changed peer, non-resumed owner, detached/replaced
  fragment adapter and live disable invalidate the pending request.
- PN is read from the current typed conversation owner. LID is not a telephone
  number. It needs an unambiguous edge in the current package's read-only
  jid_map; absent, conflicting or invalid mapping never guesses a phone number.
- Mapping runs on one daemon worker, with at most one queued task and a 1500 ms
  deadline. Timeout may resume the original only while ownership remains current.
  Late lookup results cannot revive a canceled or replaced request.
- All four sites install together. Partial installation rolls back. A retained
  callback after failed unhook stays inert; a failed instance cannot reactivate.
- Add-to-call, call links, scheduling, groups and unsupported peer types remain
  outside this selector.

Current nightly can dispose lazy features. The port implements the existing
ScreenScopedFeature descriptor: disposal clears readiness, invalidates the pending
request, unregisters listeners, cancels lookup work and shuts down the worker.
An old disposed instance cannot install again. No BaseFeature or MainHook change
is part of this focus.

## Offline compiled validation

    python3 qa/android_call_type_test.py --suite all --out /tmp/call-selector \
      --deps /path/to/verified-bundle/deps --sdk-jars /path/to/verified-bundle/sdk-jars \
      --dexkit /path/to/dexkit-2.2.0.jar

The C12 history contains 117 fixture executions. C14 retains the 29 original
selector methods and the two screen-disposal methods, and adds seven selector
methods plus four host-contract methods. The current selector suite is 114 cases
and the host suite is 36, for 150 total at API 24/28/34. None may be silently
skipped. Source/dependency identities, totals, assertion failures, errors and
skips remain recorded. Optional explicit APK inputs add 15 separate production
fingerprint file checks; see CALL_TYPE_HOST_ACCEPTANCE.md. Missing APK inputs
are reported as NOT_REQUESTED and cannot stand in for host acceptance.

Real Android dialogs, Activity/View lifecycle, Looper, Intents and SQLite are
exercised. The Activity records ACTION_DIAL instead of launching a real external
application. Host classes, Xposed registration/original invocation and the public
ScreenScopedFeature descriptor are explicit fixtures. The lazy privacy-service
fixture throws if called; unrelated privacy logic cannot silently pass.

Causal controls must compile and execute the reviewed case inventory before
their expected behavioral assertions fail: ACTION_CALL replacing ACTION_DIAL,
removed current-peer comparison, rearmed failed-install callbacks, and missing
screen-disposal invalidation. Compilation/setup failures do not reject a mutant
successfully. PN/LID identity, original continuation and cancellation have
separate positive assertions; fewer tests is not reconciliation.

## Current-host acceptance remains separate

The original investigation covered WhatsApp 2.26.40.76. C14 now pins the exact
Personal 2.26.46.82 and Business 2.26.46.83 APKs inspected through bounded static
DEX queries. Their identities, generated Runnable branches, receiver guards,
3/4-argument distinction and reproduction commands are documented in
CALL_TYPE_HOST_ACCEPTANCE.md. Unknown APK identities are rejected before host
class resolution; no heuristic expansion of multipurpose Runnable calls is used.

The current production fingerprint has been exercised against the actual APK
bytes without loading target classes. This does not establish live reflection,
AndroidX host fragment behavior, LSPosed injection, installed resource resolution,
a signed full-module APK or device behavior. Cold Windows hash measurements do
not establish Android/UI latency. Those performance and runtime gates remain
open; no real call, message, recording, account data access, permission change
or device mutation was performed by these suites.

## Review order

1. Host contract and independent fixture infrastructure.
2. Selector, registry insertion, five strings in default/es/es-419/sl and complete
   selector/disposal suite, depending on step 1.
3. Protected workflow integration consuming the current-run verified framework
   bundle, depending on both product focals and the portable dependency producer.

The workflow focus is R5. Keep each diff within R4 without removing controls.
Only hosted checks at the final reviewed focal SHA satisfy R13.
