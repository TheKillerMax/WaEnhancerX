#!/usr/bin/env python3
"""Legacy migration simulations and a guard for the production-tested preserved upgrade.

The complete preserved-store migration runs in test_preserved_message_capture.py,
which executes the production onUpgrade SQL in SQLite, including rollback.
"""
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/waenhancer/xposed/core/db'
files = {
    'edit': root / 'EditMessageStore.kt',
    'deleted': root / 'DelMessageStore.java',
}
for name, path in files.items():
    src = path.read_text()
    start = src.find('onUpgrade(')
    assert start != -1, f'{name}: missing onUpgrade'
    end = src.find('\n    fun ', start) if path.suffix == '.kt' else src.find('\n    public void insertMessage(', start)
    section = src[start:end] if end != -1 else src[start:]
    assert 'DROP TABLE' not in section, f'{name}: destructive migration'

# A verified copy-then-drop rebuild is necessary to remove SQLite's old UNIQUE
# column auto-index. Permit only its backup drop, never a drop of the live table.
preserved = (root / 'PreservedMessageStore.kt').read_text()
section = preserved[preserved.index('override fun onUpgrade('):preserved.index('    fun insertPreservedMessage(')]
assert section.count('DROP TABLE') == 1
copy = 'INSERT INTO $TABLE_NAME ($columns) SELECT $columns FROM preserved_messages_v2_backup'
drop = 'DROP TABLE preserved_messages_v2_backup'
assert copy in section and drop in section and section.index(copy) < section.index(drop)
assert 'catch (' not in section, 'Migration failures must reach SQLiteOpenHelper rollback'
qa = Path(__file__).resolve().parent
for fixture in ('test_preserved_message_capture.py', 'fixtures/PreservedMessagesChecks.kt',
                'fixtures/PreservedSelectorChecks.kt', 'fixtures/preserved_messages_android_doubles.py'):
    assert (qa / fixture).is_file(), 'Missing production SQL migration suite: ' + fixture
workflow = (qa.parent / '.github/workflows/source-qa.yml').read_text()
assert '            qa/test_preserved_message_capture.py \\' in workflow

with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE message_history (_id INTEGER PRIMARY KEY, key_id TEXT, text_data TEXT)')
    db.execute("INSERT INTO message_history(key_id,text_data) VALUES ('k1','history entry')")
    columns = {r[1] for r in db.execute('PRAGMA table_info(message_history)')}
    for col, decl in {'row_id':'INTEGER DEFAULT 0','key_id':'TEXT','text_data':'TEXT',
                      'timestamp':'INTEGER DEFAULT 0','version':'INTEGER DEFAULT 1'}.items():
        if col not in columns:
            db.execute(f'ALTER TABLE message_history ADD COLUMN {col} {decl}')
    db.execute('CREATE INDEX IF NOT EXISTS idx_hist_rowid ON message_history (row_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_hist_keyid ON message_history (key_id)')
    assert db.execute('SELECT text_data FROM message_history').fetchone()[0] == 'history entry'

with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE delmessages (_id INTEGER PRIMARY KEY, jid TEXT, msgid TEXT, timestamp INTEGER)')
    db.execute("INSERT INTO delmessages(jid,msgid,timestamp) VALUES ('g.us','mid',1234)")
    db.execute('CREATE TABLE IF NOT EXISTS delmessages (_id INTEGER PRIMARY KEY, jid TEXT, msgid TEXT, timestamp INTEGER)')
    assert db.execute('SELECT timestamp FROM delmessages WHERE msgid=?', ('mid',)).fetchone()[0] == 1234

print('Legacy edit/deleted simulations passed; preserved migration requires the separate complete production SQLite suite')
