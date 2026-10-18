# Meta AI control acceptance

The catalog previously omitted `metaai`, although the public Boolean preference and
`ChatListCustomizationsHook` still existed. The control is restored under Styles >
Home & Feed > Home layout & navigation, with the same key and a searchable catalog
entry. Existing saved values remain authoritative. The catalog now has 93 unique
entries (92 before restoring this control); this is not a count of verified hooks.

## Checks requiring the Android app

1. Seed `metaai=true`, open the screen and confirm the toggle is enabled. Toggle it
   off, leave/reopen the screen, and verify `metaai=false` remains saved.
2. Search for the localized feature title and verify navigation highlights this row.
3. Repeat in English, Spanish and Spanish Latin America. Verify compiled release
   resources retain both `feat_metaai_*` strings through the existing keep rule.
4. Restart each supported WhatsApp target, record its exact version and test whether
   the existing Meta AI view hook hides/restores the intended button.

This patch restores the missing settings/search control. It does not certify that
the existing `MetaAi` class selector matches every WhatsApp version or hide unrelated
AI surfaces. End-to-end view selection remains a separate compatibility check.
