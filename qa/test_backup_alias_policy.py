#!/usr/bin/env python3
"""Guard canonical WAEX backup keys against destructive legacy alias rewriting.

Structural QA only. For full executable Kotlin round-trips, run an Android/JVM
stub harness (JDK and kotlinc needed).
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / "app/src/main/java/com/waenhancer"
codec = (root / "core/preferences/SettingsBackupCodec.kt").read_text(encoding="utf-8")
schema = (root / "config/PreferenceSchema.java").read_text(encoding="utf-8")
keys = dict(re.findall(r'add\(entries, "([^"]+)", Type\.([A-Z_]+),', schema))
start = codec.index('private val LEGACY_ALIASES:')
stop = codec.index('\n    fun encode(', start)
aliases = dict(re.findall(r'"([^"]+)"\s+to\s+"([^"]+)"', codec[start:stop]))
resolver = codec[codec.index('private fun resolveKey('):codec.index('private fun isSensitive(')]
# Every still-declared preference keeps its own meaning in ALL backup formats.
assert 'if (PreferenceSchema.entry(originalKey) != null) return originalKey' in resolver
assert 'if (!legacyJson) return null' in resolver
assert 'val mappedKey = LEGACY_ALIASES[originalKey] ?: return null' in resolver
assert 'return mappedKey.takeIf { PreferenceSchema.entry(it) != null }' in resolver
assert 'original == null || original.type == mapped.type' not in resolver
assert 'val key = resolveKey(rawKey, legacyJson = false)' in codec
assert 'val key = resolveKey(rawKey, legacyJson = legacy)' in codec
assert 'if (legacy && rawKey != key && source.has(key)) continue' in codec, (
    'Canonical JSON values could be overwritten by an older alias')
assert 'val legacy = !root.has("schemaVersion")' in codec
assert 'Record(key, entry.type, it)' in codec
assert 'privateEditor.commit() && publicEditor.commit()' in codec
colliding = [(a, b) for a, b in aliases.items() if a in keys and b in keys]
incompatible = [(a, b) for a, b in colliding if keys[a] != keys[b]]
assert len(colliding) >= 30, 'expected current keys shadowed by legacy aliases'
assert len(incompatible) >= 4, 'expected cross-type aliases to remain protected'
for name in ('anti_revoke', 'status_text_composer', 'voice_note_speed_modifier',
             'floating_bottom_bar_scroll_hide'):
    assert any(a == name for a, _ in incompatible), name

# Equal storage types are not proof of semantic equivalence: each pair below
# controls an independent feature in the actual hook consumers.
for original, incorrectly_redirected in {
    'typing_online_toasts': 'typing_privacy',
    'hide_seen_receipts': 'hidereceipt',
}.items():
    assert keys[original] == keys[incorrectly_redirected] == 'BOOLEAN'
    assert aliases.get(original) != incorrectly_redirected, (
        f'Unsafe legacy alias redirected {original} into unrelated privacy control')

hooks = root / 'xposed/features'
toast = (hooks / 'automation/PresenceToastsHook.java').read_text()
typing = (hooks / 'privacy/TypingPrivacyHook.java').read_text()
receipts = (hooks / 'privacy/HideReceiptsHook.java').read_text()
assert 'isEnabled("typing_online_toasts", false)' in toast
assert 'isEnabled("typing_privacy", false)' in typing
assert 'isEnabled("hide_seen_receipts", false)' in receipts
assert 'isEnabled("hidereceipt", false)' in receipts
print(f'PASS: canonical keys preserved even in legacy JSON; '
      f'{len(colliding)} current-key aliases, {len(incompatible)} cross-type collisions protected; '
      'two unrelated privacy preferences kept separate')
