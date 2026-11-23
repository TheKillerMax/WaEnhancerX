#!/usr/bin/env python3
"""Independent SQLite-engine check of the narrowly scoped type-64 admin-revoke SQL.

This tests SQLite transaction semantics, NOT WhatsApp's admin-revoke call path.
"""
import sqlite3


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def database(owner=0, key="example"):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.execute("CREATE TABLE message (_id INTEGER PRIMARY KEY, key_id TEXT NOT NULL, "
               "from_me INTEGER NOT NULL, message_type INTEGER NOT NULL)")
    db.execute("INSERT INTO message VALUES (71, ?, ?, 0)", (key, owner))
    return db


def assert_original(db, owner=0, key="example"):
    require(
        db.execute("SELECT key_id, from_me, message_type FROM message WHERE _id=71").fetchone()
        == (key, owner, 0), "original message row changed"
    )


def main():
    baseline = database()
    baseline.execute("BEGIN")
    try:
        baseline.execute("INSERT INTO message VALUES(71, 'example', 0, 64)")
    except sqlite3.IntegrityError as ex:
        require("UNIQUE constraint failed" in str(ex), "baseline did not fail on PK")
        baseline.execute("ROLLBACK")
    else:
        raise AssertionError("suppressed DELETE did not reproduce the primary-key collision")
    assert_original(baseline)

    candidate = database()
    candidate.execute("BEGIN")
    target = candidate.execute(
        "SELECT key_id, from_me, message_type FROM message WHERE _id=?", (71,)
    ).fetchone()
    require(target == ("example", 0, 0), "original row identity not verified")
    deleted = candidate.execute(
        "DELETE FROM message WHERE _id=? AND key_id=? AND from_me=0", (71, "example")
    )
    require(deleted.rowcount == 1, "expected exactly one matching host DELETE")
    candidate.execute("INSERT INTO message VALUES(71, 'example', 0, 64)")
    candidate.execute("COMMIT")
    require(candidate.execute("SELECT message_type FROM message WHERE _id=71").fetchone() == (64,), "type-64 admin placeholder not committed")

    for owner, key, attempted in ((0, "example", "wrong-key"),
                                  (1, "example", "example")):
        db = database(owner, key)
        db.execute("BEGIN")
        result = db.execute(
            "DELETE FROM message WHERE _id=? AND key_id=? AND from_me=0", (71, attempted)
        )
        require(result.rowcount == 0, "guard deleted wrong key or owner")
        db.execute("COMMIT")
        assert_original(db, owner, key)

    aborted = database()
    aborted.execute("BEGIN")
    aborted.execute(
        "DELETE FROM message WHERE _id=? AND key_id=? AND from_me=0", (71, "example")
    )
    try:
        aborted.execute("INSERT INTO message VALUES(71, NULL, 0, 64)")
    except sqlite3.IntegrityError:
        aborted.execute("ROLLBACK")
    else:
        raise AssertionError("invalid placeholder did not fail")
    assert_original(aborted)
    print("PASS: SQLite PK collision reproduced; exact reconciliation commits; "
          "wrong-key/owner rejected; failure rollback restores original")


if __name__ == "__main__":
    main()
