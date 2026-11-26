# Current recording list, playback and deletion

The list always reads module-owned external/internal locations. Shared legacy
folders require the appropriate storage/audio permission; access denial cannot
hide owned files. The Recordings directory uses an API31 guard and an older-path
fallback. Enumeration/metadata reading run on IO; resume rechecks permission and
refreshes. Query/read failure preserves the previous snapshot, ends loading and
reports a localized refresh error. Cancellation is rethrown and cannot publish
late IO results or produce a failure toast. Existing metadata, filters, selection
and delete confirmation remain.
The narrowly scoped internal fallback FileProvider root permits sharing that
owned directory while retaining rejection of unrelated private files.

Each player is owned before preparation; cleanup detaches it before stop and
always attempts release. Stale completion cannot stop its replacement. A file
delete refusal retains its row and SQLite metadata. After a successful file delete,
a metadata failure removes the now-missing file's UI row and reports failure; its
stale index entry may remain. No cross-file/database rollback or atomicity is claimed.

android_call_recordings_list_test.py --out <new-directory> --deps <robolectric-jars>
--sdk-jars <instrumented-sdk-jars> --core-jar <core-1.18.0.jar> uses JDK17+,
Kotlin2.0.20 and Robolectric4.17. Thirty-five scenarios execute on API24/28/34:
105 executions. Real files, SQLite, Bundle/PFD and Core FileProvider path strategy
run behind explicit Compose/lifecycle/native MediaPlayer adapters. The complete
store/allocation helper and exact UI/provider fragments execute; the full Compose
screen, XML inflation, native playback, Binder authorization and sharing Intent do not.

The four new cases inject a real SQLite abort trigger after file deletion, a
partially successful batch, an invalid metadata table and cancellation while
real coroutine IO is held at a latch. All files and databases belong to the
fixture. Mutation controls compile permission-gated owned files, late player
ownership, false metadata-success reports and cancellation reported as failure.
Only completed JUnit assertion failures qualify.

OEM scoped storage, real navigation/rendering, legitimate APK and device acceptance
remain separate. No recording capture, audio-source or host-fingerprint change is
included. The audio-option recovery is an independent branch and merges separately.

Primary sources:
- https://developer.android.com/training/data-storage/app-specific
- https://developer.android.com/reference/android/os/Environment#DIRECTORY_RECORDINGS
- https://developer.android.com/media/platform/mediaplayer/state-resources
