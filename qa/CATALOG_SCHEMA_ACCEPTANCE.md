# Catalog and schema acceptance at nightly8

This is a metadata contract review at 9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d.
It does not certify Android hooks or device behavior.

The last count update was in bc8af5fd05f12349fa1a27ea8318592725ba808d.
Its canonical catalog contains 93 entries. The current asset and canonical
routing contain 97 distinct entries, with no entries removed. All four additions
have public BOOLEAN schema definitions and default title/description resources:

| Key | Canonical group | Destination | Schema |
| --- | --- | --- | --- |
| custom_emojis | message_controls | Conversation | BOOLEAN |
| locked_chats_message_notifications | security_vault | Privacy | BOOLEAN |
| native_floating_navigation | visual_styles | Styles / Appearance | BOOLEAN |
| remove_sticker_white_outline | message_controls | Conversation | BOOLEAN |

The existing 13 intentionally non-schema entries still consist of active legacy
UI aliases and three navigation-only routes. Backup aliases and their canonical
types are unchanged. The count remains exact; future growth requires review.

test_catalog_schema_alias_contract.py retains its unknown-key, wrong-alias,
navigation-promotion and missing-typed-preference negative controls, and now
checks the four reviewed Boolean additions explicitly. catalog_source.py
continues to reject malformed/duplicate groups, missing default resources and
unsupported canonical routing. test_style_boolean_alias_wiring.py additionally
checks the current bubble_colors to bubble_color Boolean UI alias; this is
separate from non-Boolean CSS, DPI, tab-set and choice editors.
