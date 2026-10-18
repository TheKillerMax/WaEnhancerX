# View-once download setting persistence

The Privacy catalogue renders `download_view_once`, while the existing downloader
hook consumes `downloadviewonce`. Privacy previously initialized only the latter
key and wrote only the former when the catalogue row was toggled. Returning to
the screen therefore displayed OFF, and that write did not enable the hook.

Both Privacy and Media now read the hook key through `MediaQuickSettingPolicy`,
commit both keys as one Boolean batch following an explicit toggle, and reload
the displayed value after a successful commit. Privacy also refreshes on resume.
An old display-only true value is not automatically migrated into an active hook.

Run `python3 qa/test_media_preference_sync.py`. The policy and actual preference
manager compile with JDK 17 and explicit Android doubles. The policy exercises
both alias spellings, contradictory saved values and enable/disable/reload
sequences. Manager tests cover batch persistence and failures. Source assertions
bind that tested policy to the Privacy and Media callers; they are not Compose
screen execution. Applying the updated Java harness to the original policy fails
the display-only-alias assertion after successful compilation.

On authorized Debug and optimized Release builds, verify each free/unlocked
catalogue entry under the existing authorization decisions: toggle, switch tabs,
return, recreate the activity, kill/reopen the manager and restart the host.
Confirm both stored Boolean keys, provider visibility and the downloader's
observed flag. Inject a failed preference commit and check failure feedback.
Confirm that unrelated anti-view-once, recording and privacy settings keep their
values. Resolve presentation conflicts with the pending localization PR.

This contribution does not change media retention authorization, host method
selectors, menu binding, file discovery or export. It does not establish that an
actual view-once item can be downloaded, nor recover already expired content.
