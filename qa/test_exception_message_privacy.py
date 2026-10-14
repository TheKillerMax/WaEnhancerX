#!/usr/bin/env python3
"""Static fail-closed regression for exception messages in three privacy-sensitive hooks.

This does not scan unrelated app logging; source-only, not Android instrumentation.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/waenhancer'
paths = {
    'privacy': 'xposed/features/privacy/CustomPrivacyHook.kt',
    'media': 'xposed/features/media/MediaPreviewHook.kt',
    'ipc': 'xposed/bridge/client/PreferenceBridgeClient.java',
}
src = {key:(root/path).read_text(encoding='utf-8') for key,path in paths.items()}


def hook_logs(text):
    start_marker = 'XposedBridge.log('
    offset = 0
    while True:
        at = text.find(start_marker, offset)
        if at == -1: break
        start = i = at + len(start_marker)
        depth, quote, escaped = 1, None, False
        while i < len(text):
            c = text[i]
            if quote is not None:
                if escaped: escaped=False
                elif c == '\\': escaped=True
                elif c == quote: quote=None
            elif c == '(': depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    yield text[start:i]
                    break
            i += 1
        else:
            raise AssertionError('Malformed log expression')
        offset = i + 1


UNSAFE = re.compile(r'\b(?:t|e|ex|dbError|error)\s*\.\s*getMessage\s*\('
                    r'|\$\{\s*(?:t|e|ex|dbError|error)\s*\.\s*message\s*\}'
                    r'|\$message\b')
for key,source in src.items():
    calls = list(hook_logs(source))
    assert len(calls) >= 3, f'Logging removed unexpectedly in {key}'
    for i,expr in enumerate(calls):
        assert not UNSAFE.search(expr), f'{key} may leak exception details at call {i+1}'

for probe in ('"Leak ${t.message}"', '"Leak ${dbError.message}"',
              '"Leak $message"', 'TAG + "Leak " + t.getMessage()'):
    assert UNSAFE.search(probe), 'Detector failed closed on an unsafe fixture'
for probe in ('"Failed ${t.javaClass.simpleName}"',
              'TAG + "Failed " + t.getClass().getSimpleName()'):
    assert not UNSAFE.search(probe), 'False-positive for class-only diagnostic'

assert src['privacy'].count('${t.javaClass.simpleName}') == 4
assert src['media'].count('${t.javaClass.simpleName}') >= 4
assert src['media'].count('${dbError.javaClass.simpleName}') == 2
assert 'Error: ${e.javaClass.simpleName}' in src['media']
assert src['ipc'].count('t.getClass().getSimpleName()') >= 5
assert 'error.getMessage()' not in src['ipc'], 'Persistent runtime health leaks exception text'
assert 'String detail = error.getClass().getSimpleName();' in src['ipc']
print('PASS: exception text redacted from selected custom-privacy, media and IPC logs/status')
