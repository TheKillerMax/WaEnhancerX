# HMA configuration repair: scope and acceptance

The public-source runner compiles the complete `HmaDiagnostics`, `HmaConfigPolicy`,
`HmaConfigFile` and `RootCommandRunner`, together with the actual declared-target
set. It runs 50 diagnostics/repair scenarios and 15 policy/snapshot scenarios on
each of Android API 24, 28 and 34 using Robolectric 4.17: **195 framework test
executions**. These are 65 scenarios repeated on three framework versions, not
195 devices. A separate runner executes **20 process/output checks**.

```bash
python3 qa/android_hma_test.py \
  --out /tmp/waex-hma-qa \
  --maven-repo /tmp/waex-hma-maven-cache
```

The output directory must not already exist. JDK 17 or newer, Python, Kotlin CLI
with its standard/coroutines runtime JARs, and Maven are required. The optional
`--deps` and `--sdk-jars` arguments reuse an already populated flat dependency
directory and the exact Robolectric instrumented SDK JARs. `--source-root` and
`--suite flow` can compile a historical diagnostics implementation without the
new helper classes. `--expect-assertion-failures N` accepts only the explicitly
specified number of assertion failures; setup, linkage or compilation errors do
not become successful baseline evidence.

## What is executed

- Real Android framework `Context`, package-manager interfaces, JSON and Base64
  behavior under Robolectric on the three requested API versions.
- Complete public diagnostics and repair entry points, including their IO
  dispatcher, target validation, manager discovery, result cache invalidation,
  pre/post repair manager passes, and final Boolean result.
- The complete production process runner. A test-owned executable accepts the
  runner's command protocol; it does not invoke a root manager or elevate
  privileges. Logical Android paths map to temporary files owned by this test.
- Generated config read/backup/write/restore shell logic, including size/hash checks, temporary
  file creation, owner/mode preservation, rename, cleanup and acknowledgement,
  through local `sh` and filesystem tools. The evidence records the executor UID
  without claiming that the host process is an ordinary Android app.
- Exact manager package matching, shared and unapplied template preservation,
  unrelated/default-scope template-name reservations, OSS list/preset precedence,
  complete large JSON preservation, 64 KiB limits, partial repair and injected
  filesystem/command failures.

The quick `test_hma_backup_commands.py` gate separately compiles the complete
command builder and executes 12 filesystem contracts using a JDK Base64 adapter,
an unused manager-policy link that throws if called, and an explicit SELinux
endpoint. It validates shell transactions without downloading an Android SDK or
substituting the full Android framework gate. `test_selected_upstream_hardening.py`
calls this compiled gate in place of HMA source-literal assertions and preserves
the receipt, props and call checks from upstream. `HMA_QA_COMMAND_OUT` optionally
retains its exact generated commands, logs and source/fixture identities.

## Recoverable transactions

The backup introduced in upstream `a565e1a1a50ebfe5d633e8cd0d43c6dc6025a8ac`
is preserved as `<config>.waex.bak`. Backup creation checks the live snapshot,
copies complete original bytes and metadata to a unique temporary file, verifies
the digest, and atomically replaces a regular backup destination. A symlink or
directory at the backup path is rejected. The live replacement cannot start
without the exact backup acknowledgement and independently verified backup hash.

The replacement preserves owner, mode and available SELinux label before rename.
Success requires the exact write acknowledgement and a fresh bounded snapshot
matching the whole intended document. If either check fails, guarded rollback
may copy the verified backup into another temporary file and atomically restore
it, preserving the backup itself. It only replaces a live file whose digest still
equals this attempt's exact replacement; a concurrent writer's different content
is left alone. An already unchanged original needs no rewrite. Rollback checks
its own exact acknowledgement and a fresh snapshot, and the repair still returns
false after a failed write, even when restoration succeeds.

Tests cover copied bytes/permissions, backup and live symlinks, a backup directory,
empty/suffixed/fabricated acknowledgements, failed copy or rename, stale input,
tampered backups, concurrent changes before/after replacement and before rollback,
and retained recovery copies after failed restoration. An older regular backup
is replaced by this attempt's verified pre-edit snapshot.

The command service fails on commands outside its enumerated protocol. Package
listing and force-stop are explicit service fixtures; no actual Android app is
stopped. SELinux operations are explicit fixture boundaries. The direct process
checks use local `sh` with the runner's package-private starter and never call its
public root endpoint.

## Supported path owners

| Owner/source | Accepted direct config location |
| --- | --- |
| Inspected HMA/OSS service storage | `/data/misc/hide_my_applist*/config.json` |
| Inspected legacy migration source | `/data/system/hide_my_applist*/config.json` |
| Exact known manager's own files | `/data/data/<manager>/files/config.json` |
| Canonical primary-user manager data | `/data/user/0/<manager>/files/config.json` |

`<manager>` must be exactly `com.tsng.hidemyapplist`, `org.frknkrc44.hma_oss`, or
`com.google.android.hmal`. Descendants of another app/service, additional nested
directories, unsupported users/roots, traversal components, controls and
oversized components are rejected. Discovery canonicalizes paths; read/write
commands recheck canonical identity and reject a symlinked file. Additional forks
or storage layouts require their own confirmed contracts before being accepted.

## Source basis

The rule review uses these immutable public implementations:

- [Legacy config schema, bd5466b](https://github.com/Dr-TSNG/Hide-My-Applist/blob/bd5466b37bae15e3ea2a66694e7624ce3d33479d/common/src/main/java/icu/nullptr/hidemyapplist/common/JsonConfig.kt).
- [Legacy service, bd5466b](https://github.com/Dr-TSNG/Hide-My-Applist/blob/bd5466b37bae15e3ea2a66694e7624ce3d33479d/xposed/src/main/java/icu/nullptr/hidemyapplist/xposed/HMAService.kt).
- [OSS config schema, 1fe86ce](https://github.com/frknkrc44/HMA-OSS/blob/1fe86ce2b4a6f21197e6e92d15e054d609b7d77c/common/src/main/java/icu/nullptr/hidemyapplist/common/JsonConfig.kt).
- [OSS service, 1fe86ce](https://github.com/frknkrc44/HMA-OSS/blob/1fe86ce2b4a6f21197e6e92d15e054d609b7d77c/zygote/src/main/java/org/frknkrc44/hma_oss/zygote/service/HMAService.kt).

Both services apply `extraAppList` before template rules and use the target's
whitelist mode when evaluating template membership. The template's `isWhitelist`
field is not that runtime decision. OSS evaluates `extraOppositeAppList` after the
extra list and before templates/presets, and honors the global preset exclusion
list. OSS can omit a missing template, so creating a new global name must avoid
references in other scopes/defaultConfig as well as existing template keys.

The inspector covers these JSON visibility rules for the running module package.
It does not reconstruct every service exception, dynamically populated preset,
system-app, WebView/browser, Google service, disabled-hook or per-user decision.
Legacy's missing-template behavior differs from OSS; the tests do not describe
legacy as ignoring such a reference.

## Device acceptance still required

Successful replacement means that the script returned the exact acknowledgement
and a subsequent bounded snapshot matched the intended document. It does not
establish that an HMA process reloaded the file or that WhatsApp hooks injected.
An atomic rename prevents readers seeing an incomplete replacement. Snapshot
hash checks detect observed concurrent changes; they are not an absolute
compare-and-swap against another writer in the final check/rename window.

On a disposable device with an authorized supported HMA setup, verify the
manager/service version and actual config path, original ownership/mode/SELinux
label, selected target and current module package. Confirm that the repair
preserves unrelated scopes/templates, that the service reloads the result, and
that the module's actual injection evidence changes after restarting the target.
Check failure behavior when access is denied, the file changes concurrently or
one of several files fails. A false result can accompany a partially completed
multi-file repair; this contribution reports that failure and does not promise
cross-file rollback.

No Gradle APK build, private licensing module, Android root-manager integration,
real SELinux transition, HMA Binder/service reload, native hook installation or
WhatsApp behavior is established by this public-source suite.
