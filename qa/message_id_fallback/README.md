# Message Device Source: message-ID extraction regression

## Scope and observed defects

This focuses on the two actual methods `extractMessageId(Object)` and
`extractIdFromKeyObj(Object)` of `MessageDeviceSourceHook.java`, starting from
upstream/fork `main` commit `da0ab21533029173b126ce69e2032ee9378e062e`.

The original Java regular expression is **syntactically valid**: its unescaped
`)` ends the noncapturing alternatives group after `Key\(id`, so it correctly
recognizes `messageId=`, `messageID=` and `keyId=`. It does **not** recognize
the intended `Key(id)=` spelling. Separately, scanning static fields can
return a class-level constant instead of the current message's ID, and one
inaccessible field aborts scanning before the fallback is attempted.

Expected behavior: prefer a valid instance key; ignore static constants;
continue past fields that reject reflection; and recognize the four explicit
`toString()` fallback labels without accepting unsupported delimiters.

The patch escapes the closing parenthesis in `Key(id)`, skips static fields
at both reflection levels, and isolates recoverable reflection failures per
field. It intentionally does not redesign the obfuscated WhatsApp key schema
or claim that arbitrary host `toString()` output is a reliable API.

## Local reproduction

From the repository root:

```bash
python3 qa/message_id_fallback/test_message_id_fallback.py
python3 qa/message_id_fallback/test_mutations.py
python3 -O qa/message_id_fallback/test_message_id_fallback.py
python3 -O qa/message_id_fallback/test_mutations.py
```

These scripts extract the **actual source method bodies**, embed them in a
small host-double Java harness, and compile the result with the OpenJDK 21
`jdk.compiler` module in source/target 17 mode. No Android or Xposed classes
are stubbed into the production source. A `String` input deliberately exercises
JDK module reflection restrictions; it is a local negative-control surrogate,
not evidence about a specific WhatsApp runtime.

The original method on the earlier `4750124e` baseline passed **9/13** cases and failed four named
cases (`static_message_key_ignored`, `static_key_payload_ignored`,
`fallback_Key_parenthesized`, `inaccessible_reflection_does_not_abort_fallback`).
The candidate passed **13/13**. Four targeted mutations each reintroduce one
defect; all must compile and fail a corresponding test.

## Acceptance boundary

**PASS (JVM source-fragment):** direct and inherited key extraction, four
fallback spellings, static-field exclusion, inaccessible reflection recovery,
and negative formats, with 13 unique cases and 4 mutation controls.

**NOT_VERIFIED (runtime):** exact obfuscated classes/fields in supported
WhatsApp versions, actual Android hidden-API access behavior, end-to-end
store lookup and rendered source annotation, Android personal/work profiles.
No WhatsApp message or other external event was sent. Full application builds
depend on unavailable private `:licensing` and the Android toolchain.

**NOT_VERIFIED (performance):** latency, CPU, memory, GC, jank, and battery.

This PR is independent of, but touches the same file as, the row-lifecycle
branch `fix/device-source-lifecycle-20261111`; integration must retain both
changes and rerun both suites. If host-specific key evidence contradicts these
assumptions, revert this focused patch without affecting the lifecycle fix.
