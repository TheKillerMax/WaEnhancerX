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
assert 'if (!legacyJson && original != null) return originalKey' in resolver
assert 'original == null || original.type == mapped.type' in resolver
assert 'return if (original != null) originalKey else null' in resolver
assert 'val key = resolveKey(rawKey, legacyJson = false)' in codec
assert 'val key = resolveKey(rawKey, legacyJson = legacy)' in codec
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
print(f'PASS: canonical binary and versioned JSON precedence; '
      f'{len(colliding)} current-key aliases, {len(incompatible)} cross-type collisions protected')
