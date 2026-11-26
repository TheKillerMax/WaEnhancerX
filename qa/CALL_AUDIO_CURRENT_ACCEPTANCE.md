# Explicit call-audio fallback on current nightly

This focused recovery builds on the published call-ending correction. The actual
current HookProviderIpc, source lifecycle, metadata and named event contracts are
preserved. This contributes no separate root capture engine or new host fingerprint.

In Call audio mode, an absent fallback option now means false. The user must enable
microphone fallback; an already stored true or false remains effective. This is an
intentional change from PR93's historical default true. The new switch changes
its displayed value only after putBooleans acknowledges the write. Existing
Standard mode continues to prefer microphone sources independently of that option.
AAC/Opus selection remains independent of audio-source choice.

Source setup/preparation/start failure releases that candidate; strict Call audio
mode removes the failed output instead of trying microphones. Fatal VM errors
clean up and propagate. Session diagnostics are bounded, omit call/contact/path
identity and report remote_audio=unverified even when a source starts successfully.

Run android_call_recording_audio_test.py with a new --out directory, --deps,
--sdk-jars and --dexkit inputs. JDK17+, Kotlin2.0.20 and Robolectric4.17 are required.
Twenty-seven scenarios execute on API24/28/34:81 executions. They compile the
complete recorder, public lifecycle, IPC helper, schema, stores, preference manager
and backup codec. The exact new UI initializer/callback executes through explicit
UiText/resource adapters; it is not a full Compose screen render. A real failing
SharedPreferences commit verifies both enable and disable acknowledgements.
mutate_call_recording_audio.py independently compiles three opt-in/UI regressions;
only completed JUnit assertion failures qualify, never compilation or setup errors.

Android preferences, Bundle, PFD and ContentProviderClient are real Robolectric
objects. Xposed/host discovery, scheduling, provider authorization and native media
remain controlled boundaries. Private PrivacyPrefs access throws and is counted;
no private licensing policy is implemented. No sound or encoded audio is produced.
Real Binder identity, legitimate full APK, OEM routes, LSPosed injection and exact
WhatsApp DEX acceptance remain pending. The older CALL_RECORDING_DEVICE_ACCEPTANCE
document describes those separate device requirements and retains historical data.

Platform source: https://developer.android.com/reference/android/media/MediaRecorder.AudioSource
documents VOICE_COMMUNICATION as a microphone source and the system permission
restriction for VOICE_CALL. Successful source selection cannot establish remote audio.
