# Update transfer and UI ownership

The downloader uses a unique final file per operation, not a filename/version
cache. Re-downloading a republished version therefore incurs network traffic but
cannot return the old cache or overwrite a previously delivered operation's file.
Do not delete a handed-off APK before the asynchronous installer consumes it.
Automatic cleanup or content-addressed reuse of delivered files is not implemented.

Optional release SHA-256 and size metadata reach all three download entry points.
A malformed declared digest rejects the asset, while absent legacy metadata does
not become a false verification claim. Hashing is streaming with a 32 KiB buffer;
metadata agreement is not APK signer authentication. HTTPS, 300 MiB maximum,
package/version structure validation and existing installation permission checks
remain. The updater calls the actual bounded RootCommandRunner public overload;
the regression compiles that Java class, not an invented two-argument mock API.
Root-copy size must equal the handed-off file size before PackageManager runs.

UI session cancellation revokes pending work independently of OkHttp cancellation.
Success is claimed once and invalid sessions cannot call either installer. Progress
uses a 250 ms producer gate and one pending UI runnable applying the latest value.
The measured synthetic bursts count callbacks, not battery savings or device FPS.

Run test_update_download_contract.py and test_update_session.py. The isolated
verify_stability_framework.py --mode update compiles complete updater/metadata/
sheet sources against Android, OkHttp and Compose, with only a theme adapter.
Its JUnit tests cover real JSON metadata parsing and stream integrity; installation
and real network TLS/root flows remain unverified. Existing root regression uses
unprivileged controlled subprocesses. No test installs an APK or changes user data.

Before release, test cancel/success ordering, permission prompts, concurrent
re-downloads, interrupted downloads, metadata absent/invalid, disk exhaustion,
root and normal installation, final signer verification and delivered-file cleanup
with authorized dependencies, keys and test devices. No private module is stubbed
into a production release and no claim is made for all 93 catalog features.
