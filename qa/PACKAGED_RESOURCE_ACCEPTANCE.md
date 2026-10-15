# Packaged catalog resource acceptance

The XML-source inventory is not evidence that an optimized APK retains resources
looked up by name. Keep the existing localized-catalog checks and inspect the final
release artifact separately.

## Reproduced 2.0.3 distinction

The initial Release (`1ac55f252193fda94d10135b15b49ca85cd9d24365e4049fadf56cdf875ff81f`,
8,416,040 bytes) contains the catalog asset but none of its 214 required compiled
string names. Debug (`c4531d92851c5f251614e8af822f340737981adeb7128341463f8897e3d42114`)
contains all 214. Upstream commit `6e0aa7accd8ab988205d39e3eb582c7379b49a70`
adds catalog-string keep rules; that maintainer correction is preserved, not
reimplemented here.

The republished Release (`f19d64239b493785b48540dce068a32a295f33bd33b18e48b46d168896c4ac0f`,
8,612,340 bytes) retains all 214 required strings with default values. Both APKs
still declare version 2.0.3 / 20300, so version labels alone do not identify the
artifact. These hashes identify reviewed files, not a permanently current release.

The unmodified production validator body also passed against compiled resource
tables loaded through Android 14 framework Resources in Robolectric, using Debug
and the republished Release in eleven locales including es-CL (22 valid contexts,
plus four invalid-key/package contexts). This is not full WaexApp startup, a
physical phone, native DexKit or LSPosed acceptance.

Evidence: https://github.com/TheKillerMax/WaEnhancerX/actions/runs/38802016670

## Commands

```sh
python3 qa/test_catalog_source.py
python3 qa/test_catalog_resource_keep.py
python3 qa/test_catalog_apk.py
python3 qa/verify_catalog_apk.py /path/to/final-release.apk \
  --aapt2 "$ANDROID_HOME/build-tools/36.0.0/aapt2" \
  --sha256 EXPECTED_SHA256
```

`verify_catalog_apk.py` reads the embedded catalog and AAPT2's actual binary table,
requires the target package's entries and nonempty direct default string values,
and fails on malformed inputs or unavailable tooling. It does not infer resource
presence from source XML or arbitrary string-pool matches. Unsupported dump/value
forms require review rather than a guessed pass.

The ordinary source workflow runs the checker regressions and keep-rule guard.
It does **not** build a private release or automatically inspect a newly built APK.
The artifact command above remains a mandatory pre-publication action for the
authorized release builder. Keep shrinkResources/minification, catalog validation,
licensing and signing checks enabled.

## Separate dynamic drawable scope

The refreshed public Release still lacks 13 of the 14 literal drawable names used
by MenuIconLoader and its callers. A separate focused resource-retention branch
addresses those menu/deletion icons. The optional source test is run by CI once
that contribution is merged; missing icons are not checked by the catalog-string
checker. Verify final drawable loading and rendering separately.

## Integration boundaries

This QA follow-up keeps the prior JSON/canonical-route/localized-source review
and reconciles with the current upstream keep rules. No production file differs
from reviewed upstream main in this QA branch. Preserve independent receipt and
presence work; neither its old CI results nor this resource check certify all
93 feature entries. No APK, private dependency or signing material is committed.
