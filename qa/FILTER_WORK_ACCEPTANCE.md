# Filter work and stable snapshots

Empty rule sets stop before traversing view IDs/children and before adding a new
Activity layout listener. Nonempty traversals use one immutable rule snapshot.
Reload builds the new map before volatile publication. Notification bursts share
one pending reload; an event during a running reload may queue one follow-up.
This preserves latest preference observation without repeatedly posting/removing
hundreds of queue entries. No private Pro permission or action is changed.

The original gone behavior still hides, zeros layout dimensions and posts parent
removal. Already removed views are not reconstructed when rules are disabled; this
historical behavior is outside this optimization. Actual global Xposed callbacks,
Activity ownership and long-session heap retention still require device review.

Run test_filter_work.py for controlled tree/callback counters and immutable replay.
Run verify_stability_framework.py --mode filter for compiled production parsing,
resource lookup, View layout and Handler behavior on Android 14/Robolectric. The
BaseFeature/Xposed/ActivityTracker environment is explicit; the private Pro fixture
throws if invoked rather than implementing or bypassing licensed behavior.
A fixture Context uses the package that actually owns its compiled IDs; no host
resource identifier is guessed. No native frame-time or battery gain is claimed.
