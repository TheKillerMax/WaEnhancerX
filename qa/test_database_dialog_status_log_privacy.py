#!/usr/bin/env python3
"""Fail-closed source regression for database/status diagnostics; no Android runtime implied."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]/'app/src/main/java/com/waenhancer/xposed'
FILES={
 'core/db/MessageStore.kt':4,
 'features/media/StatusDownloadHook.java':17,
}
unsafe=re.compile(
 r'\b(?:t|e|ex|failure|error)\.getMessage\s*\('
 r'|\$\{\s*(?:t|e|ex|failure|error)\.message\s*\}'
 r'|\+\s*(?:t|e|ex|failure|error)(?![\w.])'
 r'|\bLog\.getStackTraceString\s*\('
 r'|\+\s*(?:keyId|messageId|jid|chatJid|senderJid|messageText)\b'
)


def log_expressions(source):
 """Balance XposedBridge.log calls across lines, quotes and nested calls."""
 marker='XposedBridge.log('
 offset=0
 while (start:=source.find(marker,offset)) != -1:
  i=start+len(marker)
  begin=i
  depth=1
  quote=None
  escaped=False
  while i<len(source):
   char=source[i]
   if quote:
    if escaped: escaped=False
    elif char=='\\': escaped=True
    elif char==quote: quote=None
   elif char in ('"',"'"): quote=char
   elif char=='(': depth+=1
   elif char==')':
    depth-=1
    if depth==0:
     yield source[begin:i]
     break
   i+=1
  else: raise AssertionError('Unbalanced XposedBridge.log expression')
  offset=i+1


for expr, expected_unsafe in [
 ('TAG + "Error " + t.getMessage()',True),
 ('TAG + "Error " + t',True),
 ('TAG + "Error " + Log.getStackTraceString(t)',True),
 ('TAG + "native failed key=" + keyId',True),
 ('"Error ${e.message}"',True),
 ('TAG + "literal )" + t.getClass().getSimpleName()',False),
 ('"Error ${e.javaClass.simpleName}"',False),
]:
 extracted=list(log_expressions('XposedBridge.log('+expr+');'))
 assert extracted==[expr],f'Log parser lost part of expression: {expr}'
 assert bool(unsafe.search(extracted[0]))==expected_unsafe,f'Unsafe payload detector failed: {expr}'
for incomplete in ('XposedBridge.log("unterminated',
                   'XposedBridge.log(TAG + t.getMessage();'):
 try: list(log_expressions(incomplete))
 except AssertionError: pass
 else: raise AssertionError('Malformed diagnostic was accepted')

for name,count in FILES.items():
 src=(ROOT/name).read_text(encoding='utf-8')
 logs=list(log_expressions(src))
 assert len(logs)==count,(name,len(logs),count)
 for i,log in enumerate(logs):
  assert not unsafe.search(log),(name,i+1,log)
  assert ('getClass().getSimpleName()' in log or '.javaClass.simpleName}' in log
          or 'StatusPlaybackActivity not found' in log),(name,i+1,log)
for fixture,expected in [
 ('TAG + "Error " + t.getMessage()',True),
 ('TAG + "Error " + t',True),
 ('TAG + "Error " + t.getClass().getSimpleName()',False),
 ('"Error ${e.message}"',True),
 ('"Error ${e.javaClass.simpleName}"',False),
]:
 assert bool(unsafe.search(fixture))==expected,fixture

store=(ROOT/'core/db/MessageStore.kt').read_text()
dialog=(ROOT/'core/components/WaexBottomSheet.kt').read_text()
status=(ROOT/'features/media/StatusDownloadHook.java').read_text()
for operation in ('getIdFromKey','getMediaFromId','findAccountDataDir'):
 assert operation in store
for operation in ('setTitle(', 'setMessage(', 'setPositiveButton('):
 assert operation in dialog
assert 'saveMediaFile' in status
# The status helper now propagates failed closes/publication to one localized UI path.
# Keep all diagnostic counts and private-payload negative controls above intact.
start=status.index('    private void saveMediaFile(')
end=status.index('    private void copyToClipboard(', start)
save=status[start:end]
assert 'StatusMediaExporter.export(ctx, srcFile);' in save
assert 'R.string.waex_ui_failed_to_download_status' in save
assert 'R.string.waex_ui_failed_to_download_status_19426d76' not in save
assert 'failure.getClass().getSimpleName()' in save
assert 'getMessage()' not in save
print('PASS: 21 DB and status diagnostics redact private exception texts; '
      'localized status export failure retained')
