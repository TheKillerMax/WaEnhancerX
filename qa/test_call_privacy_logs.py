#!/usr/bin/env python3
"""Fail-closed source regression for exception details from call privacy hooks.

Checks diagnostic privacy and behavior retention; does not execute Android VoIP.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'app/src/main/java/com/waenhancer/xposed/features/privacy/CallPrivacyHook.java').read_text(encoding='utf-8')
logs = [line.strip() for line in source.splitlines() if 'XposedBridge.log(' in line]
assert len(logs) == 9, f'Expected 9 call-hook diagnostic sites, got {len(logs)}'
for i, line in enumerate(logs):
    assert 't.getClass().getSimpleName()' in line, f'Missing exception category at {i+1}'
    assert not re.search(r'\b(?:t|e|ex)\.getMessage\(\)|\+\s*t\s*[);]', line), (
        f'Call diagnostic could include a private JID or telephone detail at {i+1}')
assert 't.getMessage()' not in source, 'Raw exception text reappeared'
assert 'processAndShowCallInformation(wamCallObj, peerJid, rawJid)' in source
assert 'notificationManager.notify(' in source
assert 'nativeHandleIncomingXmppOffer' in source
assert 'hookIncomingCall' in source
# Detector controls: bad logs are recognized and exception class-only logs pass.
samples = [
    ('TAG + " Error: " + t.getMessage()', True),
    ('TAG + " Error: " + t.getClass().getSimpleName()', False),
    ('TAG + " Error: " + t', True),
]
for item, expected_bad in samples:
    bad = bool(re.search(r'\b(?:t|e|ex)\.getMessage\(\)|\+\s*t\s*(?:$|[);])', item))
    assert bad == expected_bad, 'Privacy detector fixture failed'
print('PASS: 9 call privacy diagnostics redacted; call observation and notification paths retained')
