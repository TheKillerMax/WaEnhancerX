# Phone-or-WhatsApp selector acceptance

This focus connects the existing public BOOLEAN call_type_controller setting
to a selector after the host has chosen its native voice/video operation. It
depends on the independently reviewed CallTypeHostContract focus. The registry
retains its current conditional registration and lifecycle policy.

## Behavior preserved from #91

- Off at startup means no host discovery and no installed selector callbacks.
- Both native voice/video operations preserve their original receiver and all
  three boolean arguments. Choosing WhatsApp continues the exact original once.
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

All original 29 selector test methods are retained. Two additional methods check
screen disposal with retained callbacks and a late LID result. The selector suite
is 93 cases at API 24/28/34; the independent eight-method host suite adds 24,
for 117 total. None may be silently skipped. The result JSON reports the exact
source/dependency identities, total, failures, assertion failures, errors and
skips. A mutation driver's --allow-test-failure preserves failed evidence but
never marks it accepted.

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

The historical static host investigation used WhatsApp 2.26.40.76 APK SHA-256
593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4.
It verified the shared classic/popup outgoing operations and activity/fragment
ownership for that exact input. Neither the contract nor this port invents a
binding for WhatsApp Personal 2.26.46.82 or Business 2.26.46.83.

Required physical acceptance therefore remains blocked pending legitimate
current-host evidence: unique native discovery, correct recipient after chat
navigation, Phone intent opening without auto-call, cancellation and same-profile
original continuation using authorized test accounts. No real call, message,
recording, account data, permission change or device mutation was performed by
the offline suite. It does not establish native DexKit matching, AndroidX host
fragment behavior, installed resource resolution, LSPosed injection or a signed
full-module APK.

## Review order

1. Host contract and independent fixture infrastructure.
2. Selector, registry insertion, five strings in default/es/es-419/sl and complete
   selector/disposal suite, depending on step 1.
3. Protected workflow integration consuming the current-run verified framework
   bundle, depending on both product focals and the portable dependency producer.

The workflow focus is R5. Keep each diff within R4 without removing controls.
Only hosted checks at the final reviewed focal SHA satisfy R13.
