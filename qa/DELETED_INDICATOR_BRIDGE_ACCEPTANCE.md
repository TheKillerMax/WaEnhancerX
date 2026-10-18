# Anti-revoke indicator values through the preference bridge

The Privacy UI correctly persists `anti_revoke_indicator` and
`deleted_message_color` as INT values. The hook previously called getString with
non-null defaults first. PreferenceBridgeClient returns those defaults for INT
values without throwing, so the integer fallback was unreachable and the user
always received default presentation choices.

Both readers now request a nullable string, retain supported legacy string
forms, and reach the integer getter when the value is stored as INT. Malformed
types/strings fall back to the existing default without escaping the reader.
Reads do not copy the full preference map, mutate settings, add hooks or change
the revoke pipeline.

Run `python3 qa/test_deleted_indicator_preference_types.py`, which also requires
`qa/test_deleted_indicator_bridge.py`. The new suite compiles the actual bridge
and the verbatim two production reader methods with explicit Android type/color
doubles. It tests INT colors and indicator types, hex/ARGB and signed-decimal
legacy colors, string types, missing values and malformed entries, both through
the real bridge and a strict SharedPreferences type-mismatch double. The original
readers compile and fail the canonical color and canonical indicator cases
separately. This is not an Android rendering or LSPosed test.

On authorized Debug and optimized Release builds, choose each indicator type and
several opaque/translucent colors, reopen/restart both processes and inspect an
actually preserved revoked message. Compare manager storage, the provider
snapshot and the rendered indicator. Test legacy backups and malformed input.
This does not establish that a status revoke was captured, that the appropriate
playback view was resolved, or that every missing Deleted Stories report is fixed.
