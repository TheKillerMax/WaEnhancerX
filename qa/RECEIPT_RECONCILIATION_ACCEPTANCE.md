# Receipt reconciliation with localized 2.0.3 main

This branch retains the original exact-recipient/message-ID allowances and bounded
pending state, the checked manual `seentick` write, and upstream's current typed
editors, localized catalog, diagnostics and status/played dispatch selectors.
The catalog is still JSON/resource-backed; it is not replaced by an old inline list.

Constructor capture now uses only the canonical serialized job `jid`. A group
participant or arbitrary constructor argument cannot be substituted when that
recipient is missing. The explicit receipt exemption uses that same recipient.
The installer regression executes the real production body with the actual JID
policy and tests missing/invalid recipients, disagreement with participant/argument,
group identity and status isolation, in addition to the previous execution-method
contract. It contains 55 checks; actual host delivery remains unverified.

Unavailable recipient capture fails closed. This may leave a legitimate receipt
pending on a host whose actual constructor contract differs; inspect that exact
build before adding a new source of identity. Do not reintroduce prefix, foreground
or last-contact guesses to make a test appear to work. Build/signing, actual host
jobs, manual menu/toolbar flows, mixed played batches and two-account privacy tests
remain required. No issue is automatically closed by source/JVM results.
