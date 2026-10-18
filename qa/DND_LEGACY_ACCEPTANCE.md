# DND legacy preference precedence

`dnd_mode=false` now overrides `dndmode=true`. The legacy key is consulted only
when the current key is absent. The hook, toolbar/menu actions, quick sheet and
Privacy initial state use the same policy. A legacy-only true value remains
visible and can be disabled by one explicit toggle. No preference is reset or
migrated automatically.

Run `python3 qa/test_dnd_preference_policy.py`. The actual Java policy is compiled
and executed over all absent/false/true combinations and toggle/recreation cases.
A compiled negative control restores the previous OR behavior and must fail the
canonical-false/legacy-true assertion. Caller integration assertions are source
checks, not Android/LSPosed execution. Repeated reads check constant work, not
device battery, throughput or frame time.

With a consenting test account and an authorized build, load legacy-only and
contradictory preferences; compare the Privacy switch, toolbar icon, menu and
quick sheet, then toggle OFF and restart the host. Check incoming/outgoing message
handling and provider updates while preserving unrelated preferences. Exercise
Ghost Mode separately: its existing explicit writes and managed controls remain
unchanged. This patch does not establish that all pending-send reports originate
from DND; packet handling, other hooks and device state need separate acceptance.
