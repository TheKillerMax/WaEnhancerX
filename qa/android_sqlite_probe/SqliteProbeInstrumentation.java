/* Derived from the owned P356 fixture (Python SHA-256
 * afa58afa8742f948840c79cf2474a1b44341f3a1f981dbf4e823ad7e875df688).
 * This APK is only a neutral SQLite fixture for disposable x86_64 Android AVDs.
 * It contains no WAEX app, WhatsApp, licensing, account, media or native code.
 */
package org.lab.waex.qa.sqlite;

import android.app.Activity;
import android.app.Instrumentation;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteStatement;
import android.os.Bundle;
import android.os.SystemClock;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.Arrays;
import java.util.Random;

public final class SqliteProbeInstrumentation extends Instrumentation {
    private static final int PAGE=96, REPS=24;
    private static final long MAX_NS=150000000000L;
    private static final String SELECT="_id,sort_ms,bytes,kind";
    private static final String OFF="SELECT "+SELECT+" FROM media INDEXED BY idx_seek ORDER BY sort_ms DESC,_id DESC LIMIT ? OFFSET ?";
    private static final String SEEK="SELECT "+SELECT+" FROM media INDEXED BY idx_seek WHERE (sort_ms<CAST(? AS INTEGER) OR (sort_ms=CAST(? AS INTEGER) AND _id<CAST(? AS INTEGER))) ORDER BY sort_ms DESC,_id DESC LIMIT ?";
    private static final String EXPR="SELECT _id,coalesce(taken_ms,added_ms),bytes,kind FROM media INDEXED BY idx_expr WHERE (coalesce(taken_ms,added_ms)<CAST(? AS INTEGER) OR (coalesce(taken_ms,added_ms)=CAST(? AS INTEGER) AND _id<CAST(? AS INTEGER))) ORDER BY coalesce(taken_ms,added_ms) DESC,_id DESC LIMIT ?";
    private long start;
    private String runNonce = "";
    private int checks;
    private void req(boolean v,String reason){if(!v)throw new IllegalStateException(reason);checks++;}
    private void budget(){if(SystemClock.elapsedRealtimeNanos()-start>MAX_NS)throw new IllegalStateException("TIME_BUDGET");}
    @Override public void onCreate(Bundle b){super.onCreate(b);runNonce=b==null?"":b.getString("run_nonce","");start();}
    @Override public void onStart(){
        start=SystemClock.elapsedRealtimeNanos();
        File f=new File(getTargetContext().getCacheDir(),"waex-qa-sqlite.sqlite");
        SQLiteDatabase db=null;
        Bundle out=new Bundle();
        boolean owned=false;
        try{
            req(runNonce.matches("[a-f0-9]{32}"),"RUN_NONCE");
            req("org.lab.waex.qa.sqlite".equals(getTargetContext().getPackageName()),"PACKAGE_ID");
            req(android.os.Process.myUid()==getTargetContext().getApplicationInfo().uid,"OWN_UID");
            req(android.os.Process.myUid()>=10000,"UNPRIVILEGED_UID");
            req((getTargetContext().getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_TEST_ONLY)!=0,"TEST_ONLY_APK");
            req(!f.exists(),"PREEXISTING_DB");
            db=SQLiteDatabase.openOrCreateDatabase(f,null);
            owned=true;
            JSONObject r=run(db);
            db.close();db=null;
            req(SQLiteDatabase.deleteDatabase(f)&&!f.exists(),"DB_CLEANUP");
            owned=false;
            r.put("checks",checks);r.put("own_db_absent",true);
            out.putString("waex_sqlite_receipt",r.toString());
            finish(Activity.RESULT_OK,out);
        }catch(Throwable e){
            if(db!=null)try{db.close();}catch(Throwable ignored){}
            if(owned)SQLiteDatabase.deleteDatabase(f);
            out.putString("waex_sqlite_error",e.getClass().getSimpleName()+":"+String.valueOf(e.getMessage()));
            out.putString("waex_sqlite_run_nonce",runNonce);
            out.putString("waex_sqlite_own_db_absent",Boolean.toString(!f.exists()));
            finish(Activity.RESULT_CANCELED,out);
        }
    }
    private static long scalar(SQLiteDatabase db,String sql){
        try(Cursor c=db.rawQuery(sql,null)){if(!c.moveToFirst())throw new IllegalStateException("NO_SCALAR");return c.getLong(0);}
    }
    private static String str(SQLiteDatabase db,String sql){
        try(Cursor c=db.rawQuery(sql,null)){if(!c.moveToFirst())throw new IllegalStateException("NO_SCALAR");return c.getString(0);}
    }
    private static long[] rows(SQLiteDatabase db,String sql,String[] args){
        long[] a=new long[PAGE*4];int i=0;
        try(Cursor c=db.rawQuery(sql,args)){
            while(c.moveToNext()){
                if(i+4>a.length)throw new IllegalStateException("PAGE_OVERFLOW");
                for(int j=0;j<4;j++)a[i++]=c.getLong(j);
            }
        }
        return Arrays.copyOf(a,i);
    }
    private static String[] anchor(long[] a){
        if(a.length!=4)throw new IllegalStateException("ANCHOR_CARDINALITY");
        return new String[]{Long.toString(a[1]),Long.toString(a[1]),Long.toString(a[0]),Integer.toString(PAGE)};
    }
    private static JSONArray plan(SQLiteDatabase db,String sql,String[] args){
        JSONArray a=new JSONArray();
        try(Cursor c=db.rawQuery("EXPLAIN QUERY PLAN "+sql,args)){
            while(c.moveToNext())a.put(c.getString(3));
        }return a;
    }
    private static double median(long[] a){
        long[] b=a.clone();Arrays.sort(b);return (b[b.length/2-1]+b[b.length/2])/2000000.0;
    }
    private static double p90(long[] a){
        long[] b=a.clone();Arrays.sort(b);return b[(int)Math.ceil(b.length*.9)-1]/1000000.0;
    }
    private void add(SQLiteDatabase db,int from,int to){
        try(SQLiteStatement s=db.compileStatement("INSERT INTO media(_id,taken_ms,added_ms,sort_ms,bytes,kind) VALUES(?,?,?,?,?,?)")){
            db.beginTransaction();
            try{
                for(int i=from;i<=to;i++){
                    if((i&1023)==0)budget();
                    long base=1600000000000L+((long)((i*7919L)%10000))*1000;
                    boolean missing=i%5==0;
                    long added=base+((i%3)*1000L);
                    s.bindLong(1,i);if(missing)s.bindNull(2);else s.bindLong(2,base);
                    s.bindLong(3,added);s.bindLong(4,missing?added:base);
                    s.bindLong(5,8192L+(i%997)*4096L);s.bindLong(6,i%7==0?1:0);
                    s.executeInsert();s.clearBindings();
                }
                db.setTransactionSuccessful();
            }finally{db.endTransaction();}
        }
    }
    private JSONObject run(SQLiteDatabase db)throws Exception{
        JSONObject result=new JSONObject();
        result.put("schema","WAEX_EMULATOR_SQLITE_PROBE_V1");
        req(android.os.Build.VERSION.SDK_INT>=24 && android.os.Build.VERSION.SDK_INT<=37,"SDK_RANGE");
        req("ranchu".equals(android.os.Build.HARDWARE) || "goldfish".equals(android.os.Build.HARDWARE),"EMULATOR_HARDWARE");
        req(Arrays.asList(android.os.Build.SUPPORTED_ABIS).contains("x86_64") && android.os.Process.is64Bit(),"X86_64_PROCESS");
        long applicationPageBytes=android.system.Os.sysconf(android.system.OsConstants._SC_PAGESIZE);
        req(applicationPageBytes==4096 || applicationPageBytes==16384,"APPLICATION_PAGE_SIZE");
        result.put("run_nonce",runNonce);
        result.put("package","org.lab.waex.qa.sqlite");
        result.put("release",android.os.Build.VERSION.RELEASE);
        result.put("hardware",android.os.Build.HARDWARE);
        JSONArray abis=new JSONArray();for(String abi:android.os.Build.SUPPORTED_ABIS)abis.put(abi);
        result.put("supported_abis",abis);
        result.put("process_is_64bit",android.os.Process.is64Bit());
        result.put("uid",android.os.Process.myUid());
        result.put("pid",android.os.Process.myPid());
        result.put("application_page_size_bytes",applicationPageBytes);
        result.put("seek_predicate","SCALAR_LEXICOGRAPHIC_SQLITE_3_9");
        result.put("sdk",android.os.Build.VERSION.SDK_INT);
        result.put("sqlite_version",str(db,"SELECT sqlite_version()"));
        result.put("sqlite_page_size_bytes",scalar(db,"PRAGMA page_size"));
        result.put("journal_mode",str(db,"PRAGMA journal_mode"));
        db.execSQL("CREATE TABLE media(_id INTEGER PRIMARY KEY,taken_ms INTEGER,added_ms INTEGER NOT NULL,sort_ms INTEGER NOT NULL,bytes INTEGER NOT NULL,kind INTEGER NOT NULL)");
        db.execSQL("CREATE INDEX idx_seek ON media(sort_ms DESC,_id DESC)");
        db.execSQL("CREATE INDEX idx_expr ON media(coalesce(taken_ms,added_ms) DESC,_id DESC)");
        JSONArray sizes=new JSONArray();
        int previous=0;
        Random rng=new Random(356);
        for(int n:new int[]{50000,100000,150000}){
            budget();
            long t0=SystemClock.elapsedRealtimeNanos();add(db,previous+1,n);
            long insertNs=SystemClock.elapsedRealtimeNanos()-t0;previous=n;
            req(scalar(db,"SELECT count(*) FROM media")==n,"ROW_COUNT");
            req(scalar(db,"SELECT count(*) FROM media WHERE sort_ms<>coalesce(taken_ms,added_ms)")==0,"NORMALIZATION");
            req(scalar(db,"SELECT count(*) FROM media WHERE taken_ms IS NULL")==n/5,"NULL_POPULATION");
            int offset=(int)(n*.8);
            String[] offArgs={Integer.toString(PAGE),Integer.toString(offset)};
            long[] key=rows(db,"SELECT "+SELECT+" FROM media INDEXED BY idx_seek ORDER BY sort_ms DESC,_id DESC LIMIT 1 OFFSET ?",new String[]{Integer.toString(offset-1)});
            String[] skArgs=anchor(key);
            long[] reference=rows(db,OFF,offArgs);
            req(reference.length==PAGE*4,"PAGE_COUNT");
            req(Arrays.equals(reference,rows(db,SEEK,skArgs)),"SEEK_EQUALITY");
            req(Arrays.equals(reference,rows(db,EXPR,skArgs)),"EXPR_EQUALITY");
            // Also validate boundaries and ties, not only the timed deep page.
            for(int k:new int[]{1,96,n/2,n-PAGE,n-1}){
                long[] a=rows(db,"SELECT "+SELECT+" FROM media INDEXED BY idx_seek ORDER BY sort_ms DESC,_id DESC LIMIT 1 OFFSET ?",new String[]{Integer.toString(k-1)});
                String[] arg=anchor(a);
                long[] expected=rows(db,OFF,new String[]{Integer.toString(PAGE),Integer.toString(k)});
                req(Arrays.equals(expected,rows(db,SEEK,arg)),"SEEK_EDGE");
                req(Arrays.equals(expected,rows(db,EXPR,arg)),"EXPR_EDGE");
            }
            String[] sql={OFF,SEEK,EXPR};String[][] args={offArgs,skArgs,skArgs};
            long[][] times=new long[3][REPS];
            for(int i=0;i<3;i++)rows(db,sql[i],args[i]);
            // Six permutations, each repeated exactly four times; shuffled blocks.
            int[][] orders={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
            int[] seq=new int[REPS];for(int i=0;i<REPS;i++)seq[i]=i%6;
            for(int i=REPS-1;i>0;i--){int j=rng.nextInt(i+1);int z=seq[i];seq[i]=seq[j];seq[j]=z;}
            for(int i=0;i<REPS;i++){
                budget();
                for(int q:orders[seq[i]]){
                    long s=SystemClock.elapsedRealtimeNanos();
                    long[] actual=rows(db,sql[q],args[q]);
                    times[q][i]=SystemClock.elapsedRealtimeNanos()-s;
                    req(Arrays.equals(actual,reference),"TIMED_EQUALITY");
                }
            }
            JSONObject row=new JSONObject();
            row.put("rows",n);row.put("offset",offset);row.put("new_rows",50000);
            row.put("insertion_ms_two_indexes",insertNs/1000000.0);
            row.put("database_pages",scalar(db,"PRAGMA page_count"));
            for(int q=0;q<3;q++){
                JSONObject m=new JSONObject();m.put("median_ms",median(times[q]));m.put("p90_ms",p90(times[q]));
                JSONArray ns=new JSONArray();for(long v:times[q])ns.put(v);
                m.put("samples_ns",ns);m.put("plan",plan(db,sql[q],args[q]));
                row.put(new String[]{"indexed_offset","materialized_seek","expression_seek"}[q],m);
            }
            sizes.put(row);
        }
        // A newly inserted newest item shifts OFFSET; the anchor's value remains stable.
        long[] first=rows(db,OFF,new String[]{Integer.toString(PAGE),"0"});
        long[] last=Arrays.copyOfRange(first,first.length-4,first.length);
        long[] next=rows(db,SEEK,anchor(last));
        db.execSQL("INSERT INTO media VALUES(150001,NULL,1900000000000,1900000000000,8192,0)");
        long[] shifted=rows(db,OFF,new String[]{Integer.toString(PAGE),Integer.toString(PAGE)});
        req(shifted[0]==last[0],"OFFSET_SHIFT_CONTROL");
        req(Arrays.equals(next,rows(db,SEEK,anchor(last))),"SEEK_STABLE_NEWEST_INSERT");
        req(Arrays.equals(next,rows(db,EXPR,anchor(last))),"EXPR_STABLE_NEWEST_INSERT");
        // Anchor deletion: strict value boundary still returns the same next page.
        db.execSQL("DELETE FROM media WHERE _id=?",new Object[]{last[0]});
        req(Arrays.equals(next,rows(db,SEEK,anchor(last))),"SEEK_ANCHOR_DELETED");
        req(Arrays.equals(next,rows(db,EXPR,anchor(last))),"EXPR_ANCHOR_DELETED");
        result.put("sizes",sizes);
        result.put("page_size_rows",PAGE);result.put("trials_each",REPS);
        result.put("null_fallback","coalesce(taken_ms,added_ms), both milliseconds");
        result.put("newest_insert_and_anchor_delete_controls",true);
        result.put("scope","OWN_SYNTHETIC_SQLITE_ANDROID_FRAMEWORK_NO_WAEX_PHOTOS_MEDIASTORE_BINDER_PROVIDER_LSPOSED");
        result.put("duration_ms",(SystemClock.elapsedRealtimeNanos()-start)/1000000.0);
        return result;
    }
}
