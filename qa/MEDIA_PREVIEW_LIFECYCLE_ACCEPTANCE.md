# Media preview lifecycle - current-nightly reconciliation

Production cleanup is byte-identical to PR #90 head 110f70413d91009a13d4354c008047a3da2b9e3f.
The nightly reference is c089458569564c241e6e2cddbd5a4de301299f28.
The fixture and boundary checks preserve the previously tested C03 integration
75a9b1fb4f3af6e5c2ed46e3e23185205f8efa01, with independent verification required
for this tree. Do not attribute the historical results to this commit.

Each preview owns its created resources, registered UI work and active call.
Replacement/dismissal cancels only that session and deletes only files it created.
A borrowed file is never owned based on its name or cache location.
The UI progress queue is coalesced and pending decoded images are released.

Run with JDK 17+, Kotlin and public pinned dependencies:
    python3 qa/android_media_preview_test.py --out /tmp/waex-preview
    python3 qa/mutate_media_preview_lifecycle.py --out /tmp/waex-preview-mutants
Use --deps, --sdk-jars, --dexkit-jar and --http-api-jar to reuse verified inputs.
The runner keeps exact artifact pins and uses the shared bounded preparer when
available; standalone nightly retains its existing size-limited pinned bootstrap.
Use new output directories. The matrix is 20 methods x API 24/28/34.
The five deliberate regressions must fail behavioral assertions after compilation.
The ActivityTracker and PrivacyPrefs boundaries are explicit and must stay unused.
Compile against real DexKit/OkHttp APIs; network/host/Xposed remain fixture boundaries.

Historical C03 local evidence: 60/60 and five detected mutations; this is not
new-tree evidence. See the historical full acceptance record at the C03 commit.
No candidate APK, WhatsApp selector/injection, actual codec/network, cryptographic
integrity, encrypted-media memory bounds, physical performance or device
compatibility is established. No change to licensing, signing or privacy decisions.
