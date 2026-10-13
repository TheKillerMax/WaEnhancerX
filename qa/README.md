# Lightweight verification and APK compatibility preflight

These checks are **diagnostics**, not evidence that WhatsApp hooks are working. They do not need the Android SDK, root, LSPosed, or a device. A full Gradle build and real-device tests are still required before merging behavior changes.

## Available scripts on this branch

| Script | Requirements | Scope |
| --- | --- | --- |
| `audit_apks.py` | Python 3.10+ standard library; **locally supplied** manager and WhatsApp APKs | ZIP CRC, manifest presence, DEX headers and SHA-1/Adler-32, ABI directory summary, 18 sampled DEX string-pool literals |
| `test_audit_apks.py` | Python 3.10+ | Synthetic malformed ZIP and DEX fixtures, correct multidex enumeration, CLI exit codes and JSON output |
| `dex_source_anchor_inventory.py` | Python 3.10+; **locally supplied** WhatsApp APK | Generate a full, source-derived list of `addUsingString` literals and report which occur in DEX string tables. An absent anchor blocks **only that literal search**, not all feature implementations. |
| `test_dex_source_anchor_inventory.py` | Python 3.10+ | Synthetic source/DEX fixtures for complete anchor discovery, strict exit status, malformed checksums and table-only matching |
| `test_hook_return_types.py` | Python 3 and JDK | Hook return/parameter contract checks |
| `test_host_class_relocations.py` | Python 3 and a **locally supplied** WhatsApp APK | Exact host class definitions for a known version (expected to change across WhatsApp releases) |
| `test_monet_wiring.py` | Python 3 | Source-level dynamic-theme wiring, not UI instrumentation |

Other tests introduced by still-open PRs are not part of upstream `main` until merged. Do not assume that unmerged scripts are available from this branch.

## Run the APK audit

From the repository root, with **your own** installed/version-matched APK copies:

```sh
python3 qa/audit_apks.py /path/to/WaEnhancerX.apk /path/to/WhatsApp.apk
python3 qa/audit_apks.py /path/to/WaEnhancerX.apk /path/to/WhatsApp.apk --json
python3 -m unittest discover -s qa -p 'test_audit_apks.py' -v
```

`--json` prints a structured report (schema version 1) with filename, SHA-256, ZIP/DEX counts, ABI folders and the sampled literal status. It intentionally does not output absolute local file paths. The APKs are only **read**, never modified or copied into the repository.

Exit codes: **0** = archive/DEX checks passed; **2** = a malformed or unreadable APK; **3** = sampled strings absent with the optional `--strict-anchors` flag. Without `--strict-anchors`, missing literals are reported but do not fail the run, because they may legitimately change across WhatsApp versions.

## Check all literal DexKit anchors from the current code

```sh
python3 qa/dex_source_anchor_inventory.py /path/to/WhatsApp.apk --source-root app/src/main/java
python3 qa/dex_source_anchor_inventory.py /path/to/WhatsApp.apk --source-root app/src/main/java --json
python3 -m unittest discover -s qa -p 'test_dex_source_anchor_inventory.py' -v
```

This second script inventories the current checked-out Java/Kotlin source, rather
than relying on the **18 historical samples** in `audit_apks.py`. Different
source revisions can have different numbers of anchors. It does not execute
DexKit or prove that the host method's class, arguments, and return value match.
Avoid claiming a feature is fixed from the presence of an anchor alone.

## What the report does *not* establish

- **DEX strings are not hooks.** The 18 literals are a historical sample, not a complete list of hooks or the result of executing DexKit's method-matcher predicates. A present string can refer to the wrong code; an absent string may have alternate resolution paths.
- **ZIP CRC and DEX checksums are integrity checks, not authentication.** They do not validate the APK signing certificate, trusted release source, package identifier, or update provenance.
- **ABI directory listing is not ELF analysis.** It does not verify 16 KiB page-size ELF segment alignment or APK ZIP entry alignment.
- **An archive is not a running app.** No output can prove compatibility with WhatsApp 2.26.39.79, WhatsApp Business, modified clones, newer/older versions, Android API levels, LSPosed, preferences IPC, UI tabs, or message-history migrations.
- **Binary manifest version detection is intentionally omitted.** Finding a version-like byte sequence inside binary AXML would not reliably identify the installed package/version.

The auditor caps the number of ZIP entries and uncompressed input size to avoid accidentally processing excessive files. Do not commit or redistribute proprietary WhatsApp APKs, DEX dumps or private signing keys. Handle diagnostic reports according to your organization's privacy and disclosure policies.

For PRs affecting runtime hooks, also run the repository's supported Android Gradle/CI checks and test representative official WhatsApp, WhatsApp Business and supported-clone targets on an authorized device.
