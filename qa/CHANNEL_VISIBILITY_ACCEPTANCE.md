# Channel visibility and lifecycle acceptance

## Product contract

The Channel recommendations hook owns a visibility binding for each resolved
View. It reconciles after host layout and reattachment, keeps the host's original
LayoutParams, and avoids repeated writes when the View is already GONE. The live
predicate remains `BaseFeature.isEnabled`: a global value takes precedence over
the package-scoped value, including an explicit global false.

Preference false stops forcing GONE. Removing the feature owner also removes its
attach/layout listeners, including when unregistration comes from a worker while
the View is detached. Cleanup uses the main Looper and resolves the weak View
reference inside the posted callback. Neither operation forces VISIBLE: an
already hidden View can remain hidden until the host next binds its visibility.

The class selector accepts one distinct View class, ignores null/non-View
candidates and duplicate references, and rejects ambiguous View classes. The
validated cache entry is `waex_channel_rec_view_class_v2`; the old entry admitted
the first unchecked match and cannot certify this stronger selection contract.

`ViewHookDispatcher.onUnregistered` connects the binding to the existing
`BaseFeature.unhookAll` owner lifecycle. The existing three shared View hooks are
unchanged. The modern Meta AI implementation in `ChatListCustomizationsHook` is
unchanged, as are the private hooking contracts.

## Behavioral evidence

The reference is the published integration at
`1f57167df3a9af5161e6f345745ddf7983d6eefc`, composed from the existing PR98,
floating/overlay PR108 and HMA dependency reuse changes.

| Experiment | API 24 / 28 / 34 result | Interpretation |
| --- | --- | --- |
| Current constructor-only Channel with four recovered oracles | 12 tests, 12 exact assertion failures | Rebinding, host parameters and missing/non-View diagnostics were broken. |
| Intermediate guard using detached `View.post` for worker cleanup | 75 tests, 3 exact assertion failures | Detached attach listeners remained registered without another attach. |
| Final complete Channel hook and helpers | 75 tests, 0 failures | Four recovered Channel tests, five recovered selector tests and sixteen lifecycle tests, each on three SDKs. |
| Eleven compiled Channel counterfactuals | 11 rejected; 66 exact assertion failures | Each control compiled and failed only its declared behavioral assertions. |
| Published Floating/overlay suite with the new dispatcher | 81 tests, 0 failures | Existing bounded method-body coverage remains green. |
| Six published Floating/overlay counterfactuals | 6 rejected; 33 exact assertion failures | Listener, background and overlay fallback oracles remain sensitive. |

The four Channel test bodies were copied literally from the recovered PR108
`ViewVisibilityBindingTest.java` (SHA-256
`ea416447a20c5d6aa39014c9c1e2984cd23d3065df1c51a53c6bfce1a3fff8d3`).
Their byte spans and hashes are preserved in the review dossier. The five-test
`ViewClassSelectorTest.java` is byte-identical to the recovered fixture. Eight
old Meta AI tests target a replaced architecture and are explicitly excluded;
they are not counted as passing tests of the current Meta AI implementation.

The added lifecycle cases cover scoped/global preference precedence, live
toggle, detach/reattach, constructor deduplication, unchanged layout no-ops,
unrelated Views and host parameters, real registrar unhooking, worker release,
release while detached without reattachment, a changed window observer,
independent/idempotent owner cleanup and the versioned cache entry.

## What is compiled and controlled

`android_channel_visibility_test.py` compiles the complete current Channel hook,
BaseFeature, HookRegistrar, ViewHookDispatcher and consumed public privacy/JID
support. It applies no product source projection and introduces no private
interface doubles. Android View behavior is real Robolectric 4.17 on the three
locked SDKs. Controlled boundaries supply discovery results and Xposed callback
dispatch; unexpected external calls fail the fixture. Bytecode inspection
confirms that Channel registers through the inherited registrar bridge.

These tests do not execute a native DexKit scan of an installed host, LSPosed
injection, a whole APK build or a physical device. Floating retains its published
three declaration-only edits for the unavailable `ScreenScopedFeature` contract;
all its method bodies are retained, but it is not complete-hook compilation.

## Reproduction

Use JDK 21 and the project Kotlin 2.0.20 compiler. Supply the same verified
framework dependency directory and public API jars used by Floating. The
Appearance workflow produces those dependencies once and reuses them for both
positive runners and both mutation suites.

```bash
python3 qa/prepare_robolectric_sdks.py \
  --out "$QA_OUT/sdk-jars" --report "$QA_OUT/sdk-bootstrap.json"
args=(
  --deps "$QA_OUT/floating/deps"
  --core-api-jar "$QA_OUT/floating/public-apis/core-1.18.0.jar"
  --annotation-api-jar "$QA_OUT/floating/public-apis/annotation-jvm-1.9.1.jar"
  --dexkit-jar "$QA_OUT/floating/public-apis/dexkit-2.2.0.jar"
  --sdk-jars "$QA_OUT/sdk-jars"
)
python3 qa/android_channel_visibility_test.py --out "$QA_OUT/channel" "${args[@]}"
python3 qa/mutate_channel_visibility.py \
  --positive-result "$QA_OUT/channel/result.json" \
  --out "$QA_OUT/channel-mutations" "${args[@]}"
```

Choose new evidence directories for each invocation. The positive Channel
runner supports Windows and Linux. The mutation supervisor requires Linux and
uses the existing PR98 process-group watchdog. Results record exact consumed
source, public-boundary and dependency identities. A positive receipt with
different source bytes is rejected before mutation execution.

## Appearance infrastructure evidence

Run `45574813182`, attempt 1, head
`b7001defb0a3a299ed6b6e913ff46071a35edb64`, initialized zero of the expected
81 tests: Robolectric's SDK fetch returned HTTP 429. Compilation and Maven graph
resolution had succeeded. The preserved artifact has SHA-256
`a902944c373cbcd75a5f076b8e57352f3a3e3497a35ec40ce75503178f133917`.

The parent later observed run `45575465174` at the reference head succeed in
3m03 with the previous workflow, before this bootstrap existed. That observation
supports an intermittent infrastructure failure; it is not evidence that this
new bootstrap fixed that public run. Validation on a published composed head
remains a separate gate.

The local shared run verified the real three canonical SDKs with zero requests
and then exercised Channel, Floating and the Floating counterfactuals offline
against those same bytes. Channel counterfactuals used the same verified SDK
identities before the shared directory was created. See
`ROBOLECTRIC_SDK_BOOTSTRAP.md` for transport controls and resource limits.
