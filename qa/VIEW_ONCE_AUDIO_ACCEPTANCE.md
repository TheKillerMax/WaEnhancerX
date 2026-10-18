# View-once Opus audio export acceptance

This path extends the current-page photo/video correction. It uses the message
already bound to the tagged audio fragment and an explicit audio exporter. It
does not query a message database on menu preparation, scan arbitrary objects
for files, use an initial-message fallback, or change view-once message state.

## Supplied host evidence

The inspected WhatsApp 2.26.40.76 antisplit APK has SHA-256
`593d1216e8f3f24303c42bb1de88ab40060128a9030c1e0e44315c9909e258a4`.
These relationships describe that input, not all WhatsApp/Business versions.

| Relationship | Observed implementation |
| --- | --- |
| Viewer | `ViewOnceViewerActivity`, with concrete boolean create/prepare menu callbacks |
| Audio branch | Message type 82 selects the `view_once_audio` fragment tag |
| Fragment manager | Inherited `0Ih.getSupportFragmentManager(): 0K6` |
| Tagged fragment | `0K6.A0Q(String): Fragment`, called by the Activity |
| Audio message binding | `ViewOnceAudioFragment.A2B(Bundle, View)`, anchored by `fMessage` |
| Message already bound | `BaseViewOnceMessageViewerFragment.A01: 1Ax` |
| Activity identity | `ViewOnceViewerActivity.A00: 1fO`, read by creation, preparation and selection |
| Media inheritance | The bound `Bac` audio class inherits `1h4` |
| Canonical media path | The independently verified `1h4.A01 → 6XI.A06(): File` chain |

The selector discovers obfuscated members from these signatures and actual
call/read-field relationships. It requires unique candidates. Matching the
complete chat, message ID and from-me identity prevents a fragment from exporting
another Activity's message. It rechecks the fragment, message object, media data
and identity after the host file accessor returns. The synthetic base-fragment
`AHX(key): File` method returns null in this host and is not used as a fallback.

A missing/ambiguous audio contract leaves the already installed photo/video
pair intact. If the second audio callback installation fails, the first audio
handle is unhooked. An error while refreshing a previously valid audio action
removes that action. The host's false return, arguments and original exception
are preserved. Fatal reflection/installation errors are not converted into an
ordinary successful optional lookup.

## Supported storage format

`GalleryMediaExporter.exportAudio` recognizes the version-1, mono/stereo,
mapping-family-0 Ogg Opus identification header. It uses `.opus`, `audio/ogg`,
`Music/WAEX`, and the Audio MediaStore collection on API 29+. Earlier Android
versions use the same existing file-copy/rename/scan contract in `Music/WAEX`.
The photo/video entrypoint rejects audio; the audio entrypoint rejects photos
and containers that do not establish this supported audio form.

The format choice follows [RFC 7845, sections 3, 5.1 and 9](https://www.rfc-editor.org/rfc/rfc7845.html).
The platform collection is documented in
[MediaStore.Audio.Media](https://developer.android.com/reference/android/provider/MediaStore.Audio.Media).
Header recognition is not full stream validation. Production does not decode
Opus, validate all Ogg pages/checksums, inspect every stream in a multiplexed
container, or prove that an evicted/encrypted host file can be recovered. Other
mapping families, future header versions, generic Ogg/Vorbis and MP4 audio are
unsupported by this path. Bytes are copied unchanged; no transcoding is added.

The single bounded export slot is shared with photos/videos. An explicit click
and `downloadviewonce` are required, including a final option check in queued
work. A worker retains the application context and selected File, not the
Activity, fragment, menu or message. A copy already inside the exporter is not
cancelled by a later setting change. A blocked copy can occupy the export slot;
this change does not add a timeout or relax permissions/licensing.

## Public-source validation

Run `python3 qa/test_view_once_audio.py` with JDK 17+. It compiles and executes
the complete audio resolver/hook, then the complete real exporter separately.
Android, host, DexKit metadata, Xposed registration and storage services are
explicit doubles. Java reflection, the bounded executor and file IO are real.
It covers complete identity, lazy paths, changed fragments/messages/data, missing
and ambiguous metadata, absent optional classes, repeated menu preparation,
false/error returns, weak listeners, stale actions, partial registration,
disable/retry, and bounded rapid taps. Storage cases check format separation,
header rejection, collection/MIME/folder choice, unchanged bytes, close before
publication, failure cleanup and retaining one descriptor across path replacement.

Pass `--dexkit-jar /path/to/dexkit-2.2.0.jar` for an additional complete-source
compile against the actual DexKit API without DexKit doubles. This does not run
DexKit native discovery. CI requires the audio entrypoint and all three fixtures;
the existing photo/video and gallery suites remain required.

`python3 qa/mutate_view_once_audio.py --out /tmp/view-once-audio-controls` compiles
unsafe variants and requires behavioral assertion failures. Compilation errors,
inert replacements or timeouts are not accepted as detections.

The storage fixture embeds two generated silence files, not private recordings
or samples extracted from WhatsApp. They were generated with FFmpeg/libopus:

```sh
ffmpeg -f lavfi -i anullsrc=r=48000:cl=mono -t 0.04 -c:a libopus -b:a 16k -vbr off mono.opus
ffmpeg -f lavfi -i anullsrc=r=48000:cl=stereo -t 0.04 -c:a libopus -b:a 16k -vbr off stereo.opus
```

The exact embedded mono file has SHA-256
`bf29355b2e494ff291c8feb69133e0abb982b1871cde665cf81a3f17708ff45e`,
and stereo has SHA-256
`576c09e03e0a23c5d5a596ebc8ca2a8cb205d10788913f9ae85af686530f730b`.
Both decode locally with FFmpeg. The test does not require FFmpeg in CI and does
not claim that the Android decoder, host cache or voice-note playback was tested.
Regeneration can change Ogg serial numbers and encoder metadata.

## Device acceptance before release

Use authorized test conversations and content. Build Debug and optimized Release
from the same reviewed commit with the legitimate signing/private dependency
configuration. Record the host, Android and LSPosed versions.

1. Enable `downloadviewonce`, open a cached received voice note and verify that
   Download appears only for a loaded audio fragment. Export it, compare saved
   bytes with the selected canonical source, and verify playback and indexing in
   a compatible audio app. Test mono and stereo inputs if the host accepts both.
2. Repeat for identical message ID strings in different chats, LID/phone
   namespaces and from-me directions. Reopen another audio message, navigate,
   close the Activity, or replace the fragment during selection. The previous
   listener must not export another message.
3. Open text view-once content, an uncommitted/missing audio fragment and a message
   whose file is not cached. No text/audio confusion or fabricated success may
   occur. Clear/evict the selected file and verify an honest failure.
4. Disable the option before tapping a retained menu and while work waits in the
   queue. Confirm no new copy begins. Tap repeatedly while copying a large video
   and verify audio cannot create extra queued work; retry after the slot clears.
5. Exercise API 24–28 missing storage permission, API 29+ provider errors, full
   storage, copy/publish failures and unsupported containers. No exception path,
   chat/message identifier or URI may leak through error logs or toasts. Confirm
   failed partial exports follow the existing cleanup contract.
6. Repeat the photo/video navigation and exact-byte checks in
   `qa/VIEW_ONCE_DOWNLOAD_ACCEPTANCE.md`. Confirm the independent menu pairs and
   storage entrypoints continue to work together in Debug and optimized Release.

Actual host injection, Android MediaProvider behavior, playback of WhatsApp
cached bytes, frame-time/RSS measurements and complete signed APK builds remain
separate acceptance steps. Text export and recovery of unavailable files are not
implemented by this audio extension.
