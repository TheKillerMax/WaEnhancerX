#!/usr/bin/env python3
"""Representative SQLite upgrade regression checks (not an Android instrumentation test)."""
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/waenhancer/xposed/core/db'
files = {
    'edit': root / 'EditMessageStore.kt',
    'preserved': root / 'PreservedMessageStore.kt',
    'deleted': root / 'DelMessageStore.java',
}
for name, path in files.items():
    src = path.read_text()
    start = src.find('onUpgrade(')
    assert start != -1, f'{name}: missing onUpgrade'
    end = src.find('\n    fun ', start) if path.suffix == '.kt' else src.find('\n    public void insertMessage(', start)
    section = src[start:end] if end != -1 else src[start:]
    assert 'DROP TABLE' not in section, f'{name}: destructive migration'

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
    db.execute('CREATE TABLE preserved_messages (_id INTEGER PRIMARY KEY, jid TEXT NOT NULL, msg_id TEXT UNIQUE, text_data TEXT)')
    db.execute("INSERT INTO preserved_messages(jid,msg_id,text_data) VALUES ('g.us','mid','preserved')")
    cols = {r[1] for r in db.execute('PRAGMA table_info(preserved_messages)')}
    if 'sender_name' not in cols:
        db.execute('ALTER TABLE preserved_messages ADD COLUMN sender_name TEXT')
    assert db.execute('SELECT text_data FROM preserved_messages').fetchone()[0] == 'preserved'
    assert 'sender_name' in {r[1] for r in db.execute('PRAGMA table_info(preserved_messages)')}

with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE delmessages (_id INTEGER PRIMARY KEY, jid TEXT, msgid TEXT, timestamp INTEGER)')
    db.execute("INSERT INTO delmessages(jid,msgid,timestamp) VALUES ('g.us','mid',1234)")
    db.execute('CREATE TABLE IF NOT EXISTS delmessages (_id INTEGER PRIMARY KEY, jid TEXT, msgid TEXT, timestamp INTEGER)')
    assert db.execute('SELECT timestamp FROM delmessages WHERE msgid=?', ('mid',)).fetchone()[0] == 1234

print('SQL migration simulations passed: edit history, preserved messages, deleted messages')