# New ART cache lifecycle fixture for API27 and API28

This fixture observes and cleans only its own new files on fresh, isolated x86_64
AVDs. It does not copy, load or invoke the canonical baseline/candidate JARs,
ExpansionMain, ClassValue tests, WAEX application code, APKs or hooks. One new
Java class is compiled once into a JAR of at most65536 bytes. Each of the two
profiles invokes it once with its own nonce and kernel boot binding.

The historical API27/API28 workloads already returned PASS. Their three staged
JARs were removed with readback, but final rmdir failed because the parent was
not empty. The original artifacts did not enumerate the remaining children.
AOSP Android8.1/9.0 sources show local oat/ISA directory preparation before OAT
and VDEX generation when the DEX parent is writable. That mechanism motivates
this experiment; it does not establish what remained in the historical runs.

## Admission and producer

The separate recovery workflow supplies the actual push branch/head and the
shared source/nonce lock through class_metadata_profile_recovery.recovery_contract.
The new cache entrypoint accepts only api27/api28; it reuses recovery_pilot's
owned BootContext and outer emulator reaping. The source checkout has an
absolute PYTHONPATH pointing to lab/qa. No environment identity is spoofed.

Build CLI: `python3 lab/qa/art_cache_recovery/build.py --sdk ... --java-home ... --out ...`.
It uses only the existing pinned JDK21/SDK36 tools and SDK metadata, never
downloads tools, and produces `artifact/cache-probe.jar` plus
`artifact/artifact-manifest.json`. The JAR contains one classes.dex and one new
class. The producer head/run/attempt are embedded in generated Java, and the
manifest records both template and generated source hashes. Compiler output
must be quiet or exactly the previously documented JDK21 source/target8 options
warning sequence for javac; D8 must be quiet. This is a build-only artifact.

Runtime CLI: `python3 lab/qa/art_cache_recovery/run.py --target api27|api28 --artifact ... --manifest-sha256 ... --out ...`.
The runtime checks the exact current producer, shared source pins, lock, one JAR
and its DEX checksum/class count before entering the controller. It generates
one nonce before boot/ADB, rejects a collision with the shared consumed ledger
without regeneration, and writes its claim before any fixture mutation.

The new process measures SDK_INT27/28, Process.is64Bit, ELF64 little-endian
EM_X86_64, sysconf page size4096, shell UID2000, fingerprint, hardware, exact
single-JAR classpath/hash and kernel boot before/after. It emits one strict JSON
line bound to producer and nonce. These measurements have no historical
workload counter and do not retroactively extend old receipts.

## Ownership and cleanup protocol

OwnedTree creates a previously absent `/data/local/tmp/waex-art-cache-probe-<nonce>`
with mode0700, fixes shell UID/GID2000 and device/inode, and creates an exclusive
bounded ownership.json marker. Its SHA binds nonce, boot, inputs and producer.
Initial inventory permits only that marker. The caller then stages the pinned
probe.jar and makes it read-only; full host readback precedes launch.

The shared helper also accepts the separate `waex-art-recovery` prefix and up to
three explicitly pinned JAR names for new pending-workload scopes. It derives
only the corresponding fixed cache basenames; it never accepts an old expansion
directory or a caller-supplied arbitrary deletion list. Its callbacks are
command(label,script,timeout), read_file(label,path,max_bytes), read_boot(). The
read_file callback must retain bounded raw bytes and transport receipts before
returning. This runner uses quiet, uncompressed ADB sync with local SHA256;
guest sha256sum is not assumed. No transport executes during module import.

Inventory descends only into approved oat/ and oat/x86_64 directories after
type/ownership checks. For the cache fixture the only extra files allowed are
oat/x86_64/probe.odex and probe.vdex. Symlinks, hardlinked files, special files,
foreign ownership/filesystem, unknown names, unexpected permissions, excessive
depth or sizes block cleanup. Zero-length known cache files are allowed and
hashed. Limits are12 entries, depth3,4MiB per file and16MiB total; inputs remain
separately pinned. The stat format must parse exactly, otherwise cleanup stops.

Two identical complete inventories precede the first deletion. Each file's
identity/hash is checked again immediately before `rm -- <exact-path>`; child
directories are removed only by exact `rmdir` after an empty-list check. The
pinned inputs and marker are removed last, then the same root inode is removed
and absence plus unchanged boot/UID are read back. There is no recursive delete,
wildcard deletion, rsync, shared-cache cleanup, root/su or security-policy change.

A launch timeout or uncertain nonzero transport completion prevents guest
cleanup. Only confirmed return0, or preparation before a launch was attempted,
allows the helper to inspect ownership for removal. Foreign or unstable contents
retain the directory and all bounded diagnostics; the existing outer controller
still reaps only its own emulator. The phase has120 seconds for preparation and
one launch, a240-second overall bound and a120-second cleanup reserve. The
invocation itself has a30-second bound and is never retried.

This is a path-based protocol inside a new isolated AVD with one fixture owner.
It checks for observed changes before every mutation and does not claim atomic
protection against a hostile concurrent process with the same shell UID.

## Outcomes

PASS requires the new identity receipt and verified absence of the owned root.
It separately reports whether local cache descendants were actually observed.
Absence of descendants means the residual hypothesis was not reproduced; it is
not evidence that the historical dirs were empty. Unknown contents, drift,
ambiguous process completion or unverified cleanup remain BLOCKED. No outcome
relabels the original API27/API28 cleanup receipts or repeats their workloads.

Offline controls use an explicit virtual filesystem and ADB/process doubles.
They qualify only these new admission, ownership and cleanup paths, never the
actual ART cache behavior. Real build and two image-specific executions remain
separate gates requiring the exact reviewed source and current producer pins.
