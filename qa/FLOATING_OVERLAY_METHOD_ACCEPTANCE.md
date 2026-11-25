# Floating-bar methods and overlay settings

## Scope and unresolved dependency

The current public-source export references
`com.waenhancer.hooking.ScreenScopedFeature` but does not contain its definition.
`FeatureRegistry` explicitly attributes `HookingEngine` and `LazyHookCoordinator`
to the private `:licensing` module. The available sources do not establish the
full `ScreenScopedFeature` contract. These references remain unchanged in product
code. No substitute interface or implementation is provided.

`qa/android_floating_bottom_bar_methods_test.py` therefore compiles a temporary
projection that removes exactly three declaration fragments: that interface's
import, its `implements` clause and `@Override` on `onScreenDisposed`. It retains
every method body and verifies that reversing those edits restores all source.
The original/projected hashes and exact edits are saved in `source-projection.json`.
Every result explicitly records `complete_hook_compilation: false`. This gate is
bounded method evidence, not full-hook or application compilation.

The real current `BaseFeature`, `HookRegistrar`, `ViewHookDispatcher`,
`HostResourceIds`, `HookErrors` and privacy support classes are compiled alongside
the projection. Android Views, layout/attachment callbacks, drawables, Intents,
preferences and permission state execute on Robolectric. Core and DexKit use real
public API JARs. Host discovery, Xposed registration/reflection and contact lookup
are fail-loud fixture boundaries; their call counter must stay zero. Host resource
names and the separate-groups selection value are explicit fixtures.

## Product behavior

An attached bar with zero height registers one layout/attachment listener pair.
The first positive layout positions the floating action button immediately and
removes both callbacks. Detachment and the existing screen-disposal traversal
also release the wait. A detached container or a container in another window
cannot initiate positioning. Disposing one window preserves another window's wait.
The existing bounded installation retries and modern styling/gesture code remain
unchanged.

Unchanged tab selection and already-hidden native indicators do not request
another explicit refresh or background replacement. When selection changes, the
exact transition owned by WAEX contributes only its last target layer. A host
replacement background remains intact as the starting drawable. Weak ownership
records do not retain the View or its drawable; they remain available to flatten
WAEX transitions after the existing screen cleanup resets selection state.

Overlay navigation uses the current context's package name. If the overlay
settings action is missing or denied, the launcher tries App info. If that route
is also unavailable it returns false so the screen displays its localized
message. Other launcher failures propagate. The existing permission query and
resume/result refresh remain authoritative. Opening Settings does not grant the
optional permission. The conditional help and explicit App info action are
presented only for the overlay item after it has been requested and remains
ungranted. Android may show a general overlay settings list on newer versions;
the launch Intent test does not certify an OEM destination screen.

## Reproduction and required results

Use JDK 21 and Kotlin 2.0.20. The framework runner accepts `--deps`,
`--core-api-jar`, `--annotation-api-jar`, `--dexkit-jar` and `--sdk-jars` for verified
offline reuse. Core 1.18.0, Annotation 1.9.1 and DexKit 2.2.0 are SHA-256 pinned;
the Core version must match the project catalog. All resolved classpath/SDK
identities and the Kotlin version are recorded. A new output directory is required.

```sh
python qa/test_overlay_permission_resources.py
python qa/android_floating_bottom_bar_methods_test.py --out /tmp/floating-positive
python qa/mutate_floating_bar_methods.py \
  --positive-result /tmp/floating-positive/result.json \
  --out /tmp/floating-negative \
  --deps /tmp/floating-positive/deps \
  --core-api-jar /tmp/floating-positive/public-apis/core-1.18.0.jar \
  --annotation-api-jar /tmp/floating-positive/public-apis/annotation-jvm-1.9.1.jar \
  --dexkit-jar /tmp/floating-positive/public-apis/dexkit-2.2.0.jar
```

The suite requires 81 executions on API 24, 28 and 34: ten original floating-bar
scenarios, ten current ownership/disposal scenarios and seven overlay scenarios,
each on three SDKs. The current pre-port source at the HMA integration snapshot
runs the original 30 floating scenarios with exactly 18 assertion failures. That
is a current-source reference, not a claim that an old V39 checkout was executed.
Use `--source-root PATH --legacy-baseline` only for that exact pre-port source.

Six causal mutations must run the full 81 cases and fail only their named
assertions: listener deduplication (6), detach release (6), screen-disposal release
(6), host-background ownership (3), overlay fallback (9), and unrelated-exception
classification (3). Compiler, dependency, runtime and missing-case failures do not
qualify as a negative control. The positive result is reused only after all of its
consumed source hashes still match. Original sources must remain unchanged.

The four resource files contain twelve source-preserved translations. The XML gate checks
matching keys, nonempty text, duplicate definitions in the same qualifier,
placeholder parity, the two Spanish variants and screen references. It does not
certify all application localization. Missing Slovenian text and a duplicate
Spanish key were separately rejected as resource controls.

## Remaining acceptance

The full hook and APK still require the real private-module contract. This gate
does not execute FeatureRegistry's interface dispatch, LSPosed, host APK selectors,
GPU blur, frame-rate measurements, the complete Compose permission screen or an
OEM restricted-settings dialog. The product remains optional-permission based.
The prepared public CI bootstrap is separate from the locally executed offline
classpath route; no new public CI run is claimed by these local results.

This focused port preserves the modern Meta AI implementation and all channel
code. It does not certify or close their separate visibility/binding behavior.

Primary platform references:

- https://developer.android.com/reference/android/view/View.OnLayoutChangeListener
- https://developer.android.com/reference/android/view/View.OnAttachStateChangeListener
- https://developer.android.com/reference/android/provider/Settings#ACTION_MANAGE_OVERLAY_PERMISSION
- https://support.google.com/android/answer/12623953
