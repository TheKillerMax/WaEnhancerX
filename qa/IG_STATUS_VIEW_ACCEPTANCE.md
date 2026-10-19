# IG status collapse and refresh acceptance

## Problem and changes

The scroll-collapse callback introduced in `b7d2ae44b3b0bf945eed810aec0cbbcaa0d7fac4`
updates the header's layout parameters before Android performs the next layout.
The old `IGStatusView.setTranslationY` override discarded every translation while
`getHeight()` was zero. Consequently, expanding a fully collapsed header could
leave its previous negative translation in place.

There is a second failure when rows are first bound, or rebound after an update,
while the header is collapsed. `HorizontalListView` measures rows only when it
adds them. Existing children with measured height zero were not measured again
when the header expanded. This occurs with the complete production
`IGStatusAdapter` on the Android framework as well as with a minimal test adapter.

The fix uses Android's standard translation behavior and remeasures existing
children when the viewport gains or changes positive height. It keeps the current
row bindings, avoiding another adapter lookup and its database/image work.

The same view classes also enqueue a new callback for every refresh, even though
each callback reads the current adapter state when it executes. Requests arriving
before that UI turn now share one update callback, and the follow-up layout pass
shares one animation callback. The immediate force-layout pass and the next-frame
pass are both retained. An update arriving during notification schedules another
turn. Detaching a view removes its pending callbacks and permits a future refresh
after reattachment.

## Reproducible framework test

Requirements: Python 3, JDK 17 or newer, Maven, and network for the first dependency
resolution. Dependencies are pinned to Robolectric 4.17, Android 14's public API
JAR, and JUnit 4.13.2. Runtime scenarios execute on Android API 24, 28, and 34.
No Android SDK installation or private licensing checkout is required.

```sh
python3 qa/android_ig_status_view_test.py \
  --out /tmp/waex-ig-status-view \
  --maven-repo /tmp/waex-ig-status-m2
```

The runner compiles the complete production `IGStatusView`, `HorizontalListView`,
and `IGStatusAdapter` files without changing their source. The test uses real
Android `View`, `FrameLayout`, `ListView`, measurement/layout, and main-looper
behavior through Robolectric. Hook data, contact resolution, menu icons,
localization, and activity tracking are explicit external-service fixtures;
attempting host activity navigation fails the fixture.

Expected result: **36 tests, zero failures**, covering twelve scenarios on each
of the three API levels:

- Translation before the first layout, and expansion from a fully collapsed header.
- Partial collapse and restoration of the requested translation.
- A burst of 10,000 update requests and a burst of 10,000 frame-refresh requests.
- Rendering the latest adapter version after a coalesced burst.
- Initial `ListView` header binding without a horizontal gesture.
- A new update arriving during adapter notification, and a rejected `post` retry.
- Cancellation on detach and successful refresh after reattachment for both views.
- Recovery from zero-height binding without another `getView` call.
- Full production adapter measurement after starting at 0, 17, 60, or 78 pixels.

The baseline at the commit above runs the same 36 tests and fails **24 assertions**
(eight failing scenarios on each API). Compilation failures, missing tests, and
framework initialization errors do not count as a successful baseline rejection:

```sh
python3 qa/android_ig_status_view_test.py \
  --source-root /path/to/b7d2ae4-worktree \
  --out /tmp/waex-ig-status-baseline \
  --maven-repo /tmp/waex-ig-status-m2 \
  --expect-assertion-failures 24
```

`--deps` can reuse an already resolved dependency directory. `--sdk-jars` accepts
a flat directory containing the matching `android-all-instrumented` JARs and uses
Robolectric's offline resolver. The runner writes source, fixture, dependency, and
SDK SHA-256 evidence together with compiler/JUnit logs. CI should retain its
top-level `*.json` and `*.log` files, excluding downloaded JARs and compiled classes.

## What the measurements establish

For a synthetic burst of 10,000 requests received before the UI processes them,
the old code posts 10,000 callbacks; the corrected code posts one. This is a
deterministic callback-count result. The test checks that the latest data still
renders and that an update received during notification is delivered separately.
Remeasuring a row does not increase the adapter's `getView` call count.

These results establish framework-level behavior. They do not measure device
frame times, prove WhatsApp hook injection, validate obfuscated status/JID
selectors, or establish the correctness of host database schemas and playback
intents. The static container registry, global scroll-observer lifetime, and
synchronous image/database work in the current adapter need their own review.

Before release, exercise the installed module on supported WhatsApp builds:
open the home screen without a horizontal gesture; collapse and expand the IG
header while status updates arrive; navigate away and back; rotate the device;
and verify row content and selected status playback. A claim about device lag or
FPS needs a device trace in addition to these framework tests.
