# Delete-for-me installation availability

The existing feature registry reports ACTIVE after `hook()` returns normally and
unhooks partial registrations when it throws. Preservation always needs a valid
entry point. Legacy entry points only open a scope and also need the database
interceptor; the current Runnable captures selected messages directly. A failed
or empty optional SQLite registration must preserve that working direct path.
This change makes availability truthful; it does not invent a new host selector.

The extended `android_preserved_dispatch_test.py` executes 123 cases on Robolectric
API 24/28/34: the original 105 plus six installation scenarios on each API. These
cover missing entry, failed entry registration, failed database registration with
real owner cleanup, an empty legacy registration set, and two direct-Runnable
captures that still persist the message when SQLite interception fails or is empty.
On unchanged production 12 new negative checks fail; on the candidate all 123 pass.
The original
message capture, scope, provider, SQLite and asynchronous acknowledgement cases
remain intact. The test Xposed engine injects registration failures explicitly.

Reproduction uses a separate checkout of the published C03 QA commit
`f0c1c47b656fae73554b9dc057d0bb2f22db7929` (tree
`a89fd0d34d97be0bd6ff1cb101cda8faacfc8a28`). Apply the adjacent
`preserve-availability-fixtures.patch` there and run its existing
`qa/android_preserved_dispatch_test.py --source-root <candidate-checkout> --out
<fresh-output>`, with the normal pinned dependencies and a complete JDK17+.
For the negative control use the unmodified C03 checkout as `--source-root` and
pass `--expect-assertion-failures 12`. The unchanged 105 cases remain in the suite.
Keeping the QA extension against its actual prerequisite avoids importing an
incomplete subset of the shared acquisition/bootstrap framework into this fix.
No private licensing implementation, native DexKit discovery, WhatsApp execution,
real message deletion, actual LSPosed injection or physical Android acceptance is
established by this framework suite. Registry failure/cleanup remains the existing
public contract; the new cases execute the real BaseFeature and HookRegistrar.
