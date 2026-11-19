"""Independent, reviewed catalog acceptance snapshot (not generated from production).

Reviewed against nightly eee15668e7dab08b4cfff90b6be441e91d73021b on 2026-11-19.
An intentional catalog change must update this snapshot only after reviewing its
schema, resource and UI route contracts. Do not derive expectations from the same
asset that catalog_source.py reads: that would hide missing or substituted keys.
This is source metadata acceptance, not proof that any hook works on a device.
"""
import re

REVIEWED_CATALOG_KEYS = tuple("""
always_online freezelastseen ghostmode_t ghostmode_r
hide_read_receipts hideread_group blueonreply seentick hide_delivery_receipts
hide_seen_receipts hideonceseen stealth_status_view autonext_status toast_viewed_status
anti_view_once download_view_once bypass_screenshot_restriction
anti_revoke preserve_own_revoke antirevokestatus antidisappearing toastdeleted
toast_viewed_message locked_chats_enhancer typearchive dnd_mode hide_chats
locked_chats_message_notifications custom_privacy ghostmode show_dndmode restartbutton open_wae
message_bomber anti_edit_messages message_device_source revokeallmessages hide_forwarded_tag
removeforwardlimit sticker_confirm_alert remove_sticker_white_outline removeseemore
stamp_copied_message doubletap2like disable_defemojis custom_emojis
jump_to_first_message unlimited_pinned_chats broadcast_tag direct_chat_dialer
inline_translation copy_status_text call_type_controller group_admin_tools status_text_composer
status_downloader media_upload_quality send_audio_as_voice_status status_video_splitter
file_size_spoofer media_preview download_profile parallel_downloading
tasker_integration voice_transcription bubble_colors custom_theme custom_time_format
custom_toolbar custom_view_dpi seen_tick_customization floating_bottom_bar
native_floating_navigation unlock_premium_customization custom_filters custom_ab_props
dotonline showonlinetext typing_online_toasts metaai channels_enhancements chat_filters
hide_ui_tabs instagram_status_layout status_style separate_groups_tabs quick_home_menu
contact_blocked_verify disable_sensor_proximity app_interface_size show_hook_toast
show_restart_sheet supported_versions bypass_version_check bootloader_spoofer
license_verification pro_features_unlock
""".split())

# Six additions since the former 92-key source assertion; hide_anti_revoke was
# intentionally removed from the catalog, giving 97 canonical keys rather than 98.
REVIEWED_ADDITION_ROUTES = {
    'parallel_downloading': ('media_utility_downloader', 2, None, 'media', False),
    'disable_defemojis': ('message_controls', 1, 'conversation', 'conversation', False),
    'custom_emojis': ('message_controls', 1, 'conversation', 'conversation', False),
    'native_floating_navigation': ('visual_styles', 4, 'appearance', 'styles', False),
    'remove_sticker_white_outline': ('message_controls', 1, 'conversation', 'conversation', False),
    'locked_chats_message_notifications': ('security_vault', 1, 'privacy', 'privacy', False),
}

META_AI_SUBCONTROLS = {
    'meta_ai_remove_home_fab': 'metaai_remove_home_fab',
    'meta_ai_remove_entry_points': 'metaai_remove_entry_points',
    'meta_ai_block_chat': 'metaai_block_chat',
}
# Explicit state and hook ownership, reviewed independently of the source.
# Resource/key presence alone cannot detect two controls exchanging setters.
META_AI_BINDINGS = {
    'meta_ai_remove_home_fab': ('removeMetaAiHomeFab', 'shouldRemoveHomeFab'),
    'meta_ai_remove_entry_points': ('removeMetaAiEntryPoints', 'shouldRemoveEntryPoints'),
    'meta_ai_block_chat': ('blockMetaAiChat', 'shouldBlockAssistantChat'),
}
REVIEWED_META_AI_RESOURCES = {'feat_metaai_title', 'feat_metaai_desc'} | set(META_AI_SUBCONTROLS)


def require_reviewed_catalog_keys(keys):
    """Reject omissions, duplicates and same-size substitutions independently."""
    keys = list(keys)
    if len(REVIEWED_CATALOG_KEYS) != 97 or len(set(REVIEWED_CATALOG_KEYS)) != 97:
        raise AssertionError('The reviewed catalog fixture itself has changed; review it explicitly')
    if len(keys) != len(set(keys)):
        raise AssertionError('FeatureCatalog has duplicate keys')
    missing = set(REVIEWED_CATALOG_KEYS) - set(keys)
    unexpected = set(keys) - set(REVIEWED_CATALOG_KEYS)
    if missing or unexpected:
        raise AssertionError(f'Reviewed catalog changed: missing={sorted(missing)}, '
                             f'unexpected={sorted(unexpected)}')


def require_reviewed_catalog_rows(rows):
    require_reviewed_catalog_keys(row['key'] for row in rows)
    by_key = {row['key']: row for row in rows}
    for key, expected in REVIEWED_ADDITION_ROUTES.items():
        row = by_key[key]
        actual = tuple(row[field] for field in
                       ('group_id', 'tab_index', 'sub_tab_id', 'tab_id', 'is_pro'))
        if actual != expected:
            raise AssertionError(f'Reviewed route changed for {key}: {actual} != {expected}')


def _source_tokens(source):
    """Keep string contents intact and ignore formatting/comments, not semantics.

    This is a bounded source-shape check, not a Kotlin/Java parser. Comments or
    quoted source-shaped text cannot satisfy a required code fragment. Nested
    block comments are unsupported and require review instead of being guessed.
    """
    pattern = r'''//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`|\w+|\S'''
    tokens = []
    for match in re.finditer(pattern, source):
        value = match.group()
        if value.startswith('//'):
            continue
        if value.startswith('/*'):
            if value.count('/*') != 1:
                raise AssertionError('Nested block comments need source-contract review')
            continue
        tokens.append(value)
    return tuple(tokens)


def _require_one_fragment(source, fragment, label):
    expected = _source_tokens(fragment)
    count = sum(source[index:index + len(expected)] == expected
                for index in range(len(source) - len(expected) + 1))
    if count != 1:
        raise AssertionError(f'Meta AI {label}: expected one reviewed block, found {count}')


def require_meta_ai_subcontrol_contract(styles, hook):
    """Pin each UI control to its own persisted key and semantic hook reader.

    The reviewed callback only updates its displayed state after that same key
    is successfully written. Unknown source shapes fail rather than falling
    back to global string-presence checks. Runtime behavior remains unverified.
    """
    if set(META_AI_BINDINGS) != set(META_AI_SUBCONTROLS):
        raise AssertionError('The reviewed Meta AI binding fixture is incomplete')
    style_tokens, hook_tokens = _source_tokens(styles), _source_tokens(hook)
    controls = []
    for resource, key in META_AI_SUBCONTROLS.items():
        state, reader = META_AI_BINDINGS[resource]
        _require_one_fragment(style_tokens, f'''
            var {state} by remember(targetEpoch) {{
                mutableStateOf(preferenceManager.getBoolean("{key}", true))
            }}
        ''', f'{resource} initial getter/state')
        control = f'''
            MetaAiRemovalSwitch(
                title = stringResource(R.string.{resource}),
                checked = {state},
                onCheckedChange = {{ enabled ->
                    if (preferenceManager.putBooleans(mapOf("{key}" to enabled))) {{
                        {state} = enabled
                    }}
                }}
            )
        '''
        _require_one_fragment(style_tokens, control, f'{resource} control binding')
        controls.append(control)
        _require_one_fragment(hook_tokens, f'''
            private boolean {reader}() {{
                return prefs.getBoolean("{key}", true);
            }}
        ''', f'{resource} semantic hook reader')
    _require_one_fragment(style_tokens, '''
        if (item.key == "metaai" && settingsState[item.key] == true) {
    ''' + '\n'.join(controls) + '}', 'enabled parent/control ownership')
