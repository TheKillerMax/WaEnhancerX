package com.waenhancer.xposed.core.db;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

/** Runs the complete production store and Android SQLiteOpenHelper against real SQLite files. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class PreservedStoreCompatibilityTest {
    private static final String NAME = "waex_preserved_messages.db";
    private static final String TABLE = "preserved_messages";
    private Context context;
    private PreservedMessageStore store;

    @Before public void before() {
        context = RuntimeEnvironment.getApplication();
        assertTrue(!context.getDatabasePath(NAME).exists() || context.deleteDatabase(NAME));
    }

    @After public void after() {
        if (store != null) store.close();
        context.deleteDatabase(NAME);
    }

    private PreservedMessageStore openStore() throws Exception {
        Constructor<PreservedMessageStore> ctor = PreservedMessageStore.class.getDeclaredConstructor(Context.class);
        ctor.setAccessible(true);
        store = ctor.newInstance(context);
        return store;
    }

    /** Version 3 was merged and then reverted; only its UNIQUE key differs from version 2. */
    private SQLiteDatabase create(int version) {
        SQLiteDatabase db = context.openOrCreateDatabase(NAME, Context.MODE_PRIVATE, null);
        db.execSQL("CREATE TABLE " + TABLE + " (_id INTEGER PRIMARY KEY AUTOINCREMENT," +
                "jid TEXT NOT NULL,contact_name TEXT," + (version == 1 ? "" : "sender_name TEXT,") +
                "msg_id TEXT" + (version == 3 ? "" : " UNIQUE") + ",text_data TEXT," +
                "timestamp INTEGER DEFAULT 0,from_me INTEGER DEFAULT 0,is_group INTEGER DEFAULT 0" +
                (version == 3 ? ",UNIQUE(jid,msg_id,from_me)" : "") + ")");
        db.setVersion(version);
        return db;
    }

    private static void seed(SQLiteDatabase db, long row, String jid, String id, int direction, String text) {
        db.execSQL("INSERT INTO " + TABLE + "(_id,jid,contact_name,msg_id,text_data,timestamp,from_me,is_group)" +
                " VALUES(?,?,?, ?,?,?,?,?)", new Object[]{row, jid, "Chat " + jid, id, text, 1000L + row, direction, 1});
    }

    private static List<List<String>> query(SQLiteDatabase db, String sql) {
        List<List<String>> result = new ArrayList<>();
        try (Cursor cursor = db.rawQuery(sql, null)) {
            while (cursor.moveToNext()) {
                List<String> row = new ArrayList<>();
                for (int i = 0; i < cursor.getColumnCount(); i++) row.add(cursor.isNull(i) ? null : cursor.getString(i));
                result.add(row);
            }
        }
        return result;
    }

    private static List<List<String>> schema(SQLiteDatabase db) {
        return query(db, "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name");
    }

    private static List<List<String>> rows(SQLiteDatabase db) {
        return query(db, "SELECT * FROM " + TABLE + " ORDER BY _id");
    }

    private static List<List<String>> sequence(SQLiteDatabase db) {
        return query(db, "SELECT name,seq FROM sqlite_sequence ORDER BY name");
    }

    @Test public void createsFreshDatabaseAndReadsTheSavedMessage() throws Exception {
        // Keep the existing eight-argument constructor callable by Java consumers.
        PreservedMessageStore.StoredMessage constructed = new PreservedMessageStore.StoredMessage(
                "external", "12345@g.us", "Group", "Sender", "text", 100L, false, true);
        assertEquals("external", constructed.getId());
        openStore().insertPreservedMessage("12345@g.us", "Group", "Sender", "fresh", "hello", 100L, false, true);
        List<PreservedMessageStore.StoredMessage> records = store.getAllPreservedMessages();
        assertEquals(1, records.size());
        assertEquals("fresh", records.get(0).getId());
        assertEquals("Sender", records.get(0).getSenderName());
        assertEquals("hello", records.get(0).getText());
        assertFalse(records.get(0).isFromMe());
        assertTrue(records.get(0).isGroup());
        assertTrue(query(store.getReadableDatabase(), "SELECT sql FROM sqlite_master WHERE name='preserved_messages'")
                .get(0).get(0).contains("msg_id TEXT UNIQUE"));
    }

    @Test public void upgradesVersion1WithoutLosingRowsOrSequence() throws Exception {
        List<List<String>> previousSequence;
        try (SQLiteDatabase db = create(1)) {
            seed(db, 41, "12345@g.us", "old-one", 0, "legacy content");
            previousSequence = sequence(db);
        }
        List<PreservedMessageStore.StoredMessage> records = openStore().getAllPreservedMessages();
        assertEquals(1, records.size());
        assertEquals("legacy content", records.get(0).getText());
        assertEquals("", records.get(0).getSenderName());
        assertEquals(previousSequence, sequence(store.getReadableDatabase()));
        assertEquals("41", rows(store.getReadableDatabase()).get(0).get(0));
        assertEquals(9, query(store.getReadableDatabase(), "PRAGMA table_info(preserved_messages)").size());
    }

    @Test public void version2KeepsLegacySchemaAllColumnsAndAutoincrement() throws Exception {
        List<List<String>> beforeSchema, beforeRows, beforeSequence;
        try (SQLiteDatabase db = create(2)) {
            seed(db, 71, "12345@g.us", "old-two", 1, "all columns survive");
            db.execSQL("UPDATE preserved_messages SET sender_name='Me'");
            db.execSQL("UPDATE sqlite_sequence SET seq=200 WHERE name='preserved_messages'");
            beforeSchema = schema(db); beforeRows = rows(db); beforeSequence = sequence(db);
        }
        openStore();
        assertEquals(1, store.getAllPreservedMessages().size());
        SQLiteDatabase db = store.getReadableDatabase();
        assertEquals(beforeSchema, schema(db)); assertEquals(beforeRows, rows(db)); assertEquals(beforeSequence, sequence(db));
        store.insertPreservedMessage("67890@g.us", "Another group", "Sender", "new-two", "new", 300L, false, true);
        assertEquals(2, store.getAllPreservedMessages().size());
        assertEquals("201", query(db, "SELECT _id FROM preserved_messages WHERE msg_id='new-two'").get(0).get(0));
    }

    @Test public void version3OpensWithoutRebuildingOrLosingDistinctMessages() throws Exception {
        List<List<String>> beforeSchema, beforeRows, beforeSequence;
        try (SQLiteDatabase db = create(3)) {
            seed(db, 51, "12345@g.us", "shared-id", 0, "received");
            seed(db, 52, "12345@g.us", "shared-id", 1, "sent");
            seed(db, 53, "67890@g.us", "shared-id", 0, "other chat");
            db.execSQL("UPDATE preserved_messages SET sender_name='Known sender'");
            beforeSchema = schema(db); beforeRows = rows(db); beforeSequence = sequence(db);
        }
        assertEquals("Reverting a hook must not make a version-3 vault appear empty", 3, openStore().getAllPreservedMessages().size());
        SQLiteDatabase db = store.getReadableDatabase();
        assertTrue("Never decrease the published schema version", db.getVersion() > 3);
        assertEquals(beforeSchema, schema(db)); assertEquals(beforeRows, rows(db)); assertEquals(beforeSequence, sequence(db));
        store.close(); store = null;
        assertEquals(3, openStore().getAllPreservedMessages().size());
        assertEquals(beforeRows, rows(store.getReadableDatabase()));
    }

    @Test public void version3CanAppendAndReplaceOnlyTheExistingTuple() throws Exception {
        try (SQLiteDatabase db = create(3)) {
            seed(db, 61, "12345@g.us", "same", 0, "original");
            seed(db, 62, "12345@g.us", "same", 1, "other direction");
            seed(db, 63, "67890@g.us", "same", 0, "other chat");
        }
        openStore().insertPreservedMessage("12345@g.us", "Chat", "Sender", "same", "replacement", 400L, false, true);
        assertEquals(3, store.getAllPreservedMessages().size());
        assertEquals("replacement", query(store.getReadableDatabase(), "SELECT text_data FROM preserved_messages WHERE jid='12345@g.us' AND from_me=0").get(0).get(0));
        assertEquals("other direction", query(store.getReadableDatabase(), "SELECT text_data FROM preserved_messages WHERE _id=62").get(0).get(0));
        assertEquals("other chat", query(store.getReadableDatabase(), "SELECT text_data FROM preserved_messages WHERE _id=63").get(0).get(0));
        store.insertPreservedMessage("12345@g.us", "Chat", "Sender", "new-three", "appended", 500L, false, true);
        assertEquals(4, store.getAllPreservedMessages().size());
    }

    @Test public void unknownFutureVersionIsRejectedWithoutChangingAnything() throws Exception {
        List<List<String>> beforeSchema, beforeRows, beforeSequence;
        try (SQLiteDatabase db = create(3)) {
            seed(db, 91, "12345@g.us", "future", 0, "retain future data");
            db.setVersion(5);
            beforeSchema = schema(db); beforeRows = rows(db); beforeSequence = sequence(db);
        }
        openStore();
        try { store.getWritableDatabase(); fail("Unknown future database version was admitted"); }
        catch (SQLiteException expected) { assertTrue(expected.getMessage().contains("downgrade")); }
        try (SQLiteDatabase db = context.openOrCreateDatabase(NAME, Context.MODE_PRIVATE, null)) {
            assertEquals(5, db.getVersion()); assertEquals(beforeSchema, schema(db));
            assertEquals(beforeRows, rows(db)); assertEquals(beforeSequence, sequence(db));
        }
    }

    @Test public void durableRowKeysCoverDuplicateLogicalAndNullMessageIds() throws Exception {
        try (SQLiteDatabase db = create(3)) {
            seed(db, 101, "12345@g.us", "same", 0, "received");
            seed(db, 102, "12345@g.us", "same", 1, "sent");
            seed(db, 103, "12345@g.us", null, 0, "legacy null one");
            seed(db, 104, "12345@g.us", null, 0, "legacy null two");
        }
        List<PreservedMessageStore.StoredMessage> records = openStore().getAllPreservedMessages();
        assertEquals(4, records.size());
        // Reflection lets the unchanged baseline compile and expose its real downgrade failure.
        Method key = PreservedMessageStore.StoredMessage.class.getMethod("getStorageId");
        Set<Long> actual = new HashSet<>();
        for (PreservedMessageStore.StoredMessage row : records) actual.add((Long) key.invoke(row));
        assertEquals(new HashSet<>(java.util.Arrays.asList(101L, 102L, 103L, 104L)), actual);
        assertEquals("same", records.get(0).getId());
        assertEquals("", records.get(2).getId());
        store.close(); store = null;
        Set<Long> reopened = new HashSet<>();
        for (PreservedMessageStore.StoredMessage row : openStore().getAllPreservedMessages()) reopened.add((Long) key.invoke(row));
        assertEquals(actual, reopened);
    }
}
