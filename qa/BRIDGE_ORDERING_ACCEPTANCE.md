# Preference bridge snapshot ordering

The bridge keeps confirmed state separate from accepted optimistic writes. A provider/disk read is admitted only when no edits are pending, no edit completed/started since its query began, and no newer query began. Writes are queued in registration order; completion cannot discard a newer optimistic edit. Explicit commit results and authorization stay unchanged.

Run `python3 qa/test_bridge_ordering.py`, the existing bridge contract, and `python3 qa/mutate_bridge_ordering.py --out /tmp/bridge-negative-controls`. Tests use the full production Java bridge with explicit Android/provider/Handler substitutes. Seven barrier-controlled scenarios cover reads before/after apply, old commit versus new apply, denial, reused editor clear, reverse read completion and clear/remove/set bursts. This is not Binder or Android disk persistence.

The pending journal and executor hold work until provider calls finish. Queue backpressure and Binder timeouts are unchanged, and replay may cost more for very large write bursts. No FPS, RAM or battery improvement is claimed. A commit interrupted while waiting can still persist; false is not a distributed rollback guarantee.

With authorized builds, verify manager/host round trips, independent processes, protected-key rejections, disk-only fallback, denied/unavailable provider, rapid edits, multiple threads, empty snapshots, real observer delivery and process restart. Issue #48 still needs a device/configuration-specific reproduction; these tests do not establish its cause. No reset, schema migration, permission, entitlement or signing changes.
