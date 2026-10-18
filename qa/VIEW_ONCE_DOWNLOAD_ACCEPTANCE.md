# Current-page view-once export acceptance

The photo/video hook follows the same selection and file accessor used by the host
media menu. It does not walk arbitrary fields, accept every `X.*` argument as a
message, select the first resource-ID match, or reuse the initial message after a
page change. Missing or ambiguous relationships leave the optional hook uninstalled.

## Inspected host contract

These observations come from the supplied WhatsApp 2.26.40.76 antisplit APK,
SHA-256 `593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4`.
They describe that input, not every WhatsApp/Business release or an official
distribution signature.

| Relationship | Observed member |
| --- | --- |
| Media menu creation | `MediaViewFragment.A1u(MenuInflater, Menu)` |
| Media menu preparation | `MediaViewFragment.A1t(Menu)` |
| Current page | `MediaViewBaseFragment.A07` → `ViewPager.getCurrentItem()` |
| Current message | `MediaViewFragment.A04(fragment, index)` → `1h4` |
| Host menu click | `MediaViewMenu.A0C(MenuItem, Fragment, 1h4, int)` |
| Message identity | `1Ax.A0j` → immutable `1fO` chat, ID and from-me fields |
| Media data | `1h4.A01` → `6XI` |
| Canonical file | `6XI.A06()` → `File` |

The runtime selector discovers these members from signature and call/field
relationships. It does not hardcode the obfuscated names above. The file accessor
can resolve a stored relative path when its cached `File` field is null. The
zero-argument `MediaViewFragment.A2b()` instead resolves the initial message; it
cannot stand in for current-page selection.

`ViewOnceViewerActivity` in this input hosts text and type-82 audio fragments.
Its separate audio path is documented in `qa/VIEW_ONCE_AUDIO_ACCEPTANCE.md`.
The photo/video route does not add a gallery action to that Activity. Text export
is not implemented, and Opus audio requires the distinct, verified audio selector
and explicit audio storage route.

## Public-source checks

Run `python3 qa/test_view_once_download.py` with JDK 17 or later. It compiles the
complete production hook and resolvers with explicit Android, host and DexKit metadata doubles;
real Java reflection and a real `ThreadPoolExecutor` execute selection, navigation,
metadata ambiguity, weak listener targets, configuration changes, failure/retry,
partial callback-registration rollback, and offer-then-worker-start failure cases.
If the second menu callback fails to install, the returned first handle is unhooked;
a fatal installation error propagates after this cleanup. Repeated menu preparation performs no
message/file resolution. A compiled listener owns no fragment, Activity or menu.

Pass `--dexkit-jar /path/to/dexkit-2.2.0.jar` to additionally compile these production
files against the actual DexKit 2.2.0 API without DexKit doubles. That check still
does not execute the native bridge. The fixture omits constructor edges and avoids
loading unrelated optional editor/sharing service classes during discovery.

`python3 qa/mutate_view_once_download.py --out /tmp/view-once-negative-controls`
requires ten deliberately unsafe variants to compile and fail a behavioral
assertion. Compilation errors, timeouts and unchanged substitutions do not count.

Run `python3 qa/test_gallery_export.py` separately. That existing suite compiles
the real exporter, copies real files and exercises the existing photo/video contracts with Android storage
doubles. The hook suite uses an exporter double and therefore does not establish
MediaStore publication, permissions, decoder support or on-device durability.

## Device acceptance before release

Use authorized test conversations and media. Build Debug and optimized Release
from the same reviewed commit with the legitimate private dependency and signing
configuration. Repeat on the intended host, Android and LSPosed versions.

1. With `downloadviewonce` off, verify that no module export action remains after
   the menu refreshes. Retain a prior menu and disable the setting before tapping;
   no export may occur. Enable it and verify the action in the real photo/video menu.
2. Open at least two photos and a video with distinctive contents. Navigate from
   the initial item to each subsequent item and back before tapping. Check the
   saved bytes/content against the item selected at the click. Repeat with equal
   message-ID strings in different chats, LID/phone namespaces and from-me directions.
3. Test a newly downloaded item whose media data has not yet cached its `File`
   object, and an item containing a thumbnail or unrelated path. Only the host's
   canonical media file is eligible. Unavailable, removed or unsupported content
   must report failure without exporting another file.
4. Navigate, replace the pager/data or close the viewer during selection. A
   contradictory selection must not export. Once the user explicitly starts a
   resolved export, copying that selected file may finish after navigation; the
   worker retains application context and the selected path, not the viewer.
5. Tap rapidly while a large copy is running. Only one export is accepted at a
   time. Disable the option while work is queued and verify that it is skipped;
   the option does not cancel a copy that already entered the exporter.
6. Exercise missing permissions on API 24–28, API 29+ publication, full storage,
   source eviction, provider failure and unsupported containers. Failure must not
   be announced as success, incomplete rows/files must follow the existing exporter
   cleanup contract, and logs/toasts must not include exception path/URI payloads.
7. Remove the optional download icon resource and verify that the text action
   remains usable. With missing or ambiguous selector relationships, the optional
   hook must stay unavailable. Ordinary host viewing, menu actions and sending
   must continue in both cases.

No Android frame-time/RSS claim follows from the JVM checks. The current-message
lookup and canonical path accessor run for an explicit click on the UI caller;
file inspection and copying run on the dedicated worker. A blocked copy has no
new timeout and can keep the single export slot occupied. This patch does not
transcode media, recover files no longer held by WhatsApp, alter view-once state,
change licensing, or bypass Android permissions.
