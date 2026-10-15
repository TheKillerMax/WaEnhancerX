#!/usr/bin/env python3
"""Test real process-local cache invalidation, ordering and bounded concurrency on the JVM."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEST = r'''
package com.waenhancer.xposed.features.automation;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public final class TestPresenceInvalidation {
 static int checks;
 static void check(boolean value,String name){if(!value)throw new AssertionError(name);checks++;}
 public static void main(String[]args)throws Exception{
  String pn="900001@s.whatsapp.net",lid="123456@lid",other="900002@s.whatsapp.net";
  PresenceStateStore.invalidateAll();
  check(PresenceStateStore.update(pn,true),"initial online transition");
  PresenceStateStore.State first=PresenceStateStore.get(pn);
  check(first.known&&first.online&&first.changedAtMillis>0,"known observation");
  check(!PresenceStateStore.update(pn,true),"repeat is not transition");
  PresenceStateStore.State repeated=PresenceStateStore.get(pn);
  check(repeated.revision>first.revision&&repeated.transitionRevision==first.transitionRevision&&repeated.changedAtMillis==first.changedAtMillis,"repeat preserves transition but refreshes revision");
  PresenceStateStore.update(pn,false);
  check(!PresenceStateStore.isCurrentOnline(pn,first.transitionRevision),"offline invalidates pending online");
  PresenceStateStore.update(pn,true);
  check(PresenceStateStore.get(pn).transitionRevision>first.transitionRevision,"new transition identity independent of wall time");
  PresenceStateStore.update(other,true);PresenceStateStore.invalidate(lid);
  PresenceStateStore.State unknown=PresenceStateStore.getLatest(Arrays.asList(pn,lid));
  check(!unknown.known&&!unknown.online&&unknown.changedAtMillis==0,"denial masks older explicit alias without fabricated last seen");
  check(PresenceStateStore.getLatest(Arrays.asList(lid,pn))==unknown,"candidate order cannot undo denial");
  check(PresenceStateStore.get(other).online,"unrelated contact isolated");
  PresenceStateStore.update(pn,true);
  check(PresenceStateStore.getLatest(Arrays.asList(lid,pn)).known,"later actual observation restores known state");
  PresenceStateStore.invalidateAll();PresenceStateStore.update(pn,true);PresenceStateStore.invalidate(lid);
  for(int i=0;i<2046;i++)PresenceStateStore.update("entry"+i+"@lid",true);
  for(int i=0;i<1000;i++)PresenceStateStore.get(pn);
  PresenceStateStore.update("next@lid",true);
  check(PresenceStateStore.get(pn)==null&&PresenceStateStore.get(lid)!=null,"reads must not preserve an older alias after a denial");
  PresenceStateStore.update("next2@lid",true);
  check(PresenceStateStore.getLatest(Arrays.asList(pn,lid))==null,"tombstone eviction must not resurrect the older observation");
  PresenceStateStore.invalidateAll();PresenceStateStore.update(pn,true);
  for(int i=0;i<2047;i++)PresenceStateStore.update("other"+i+"@lid",true);
  PresenceStateStore.update(pn,true);PresenceStateStore.update("tail@lid",true);
  check(PresenceStateStore.get(pn)!=null&&PresenceStateStore.get("other0@lid")==null,"a real repeated observation refreshes retention");
  AtomicInteger signals=new AtomicInteger();
  PresenceStateStore.Listener broken=(j,s)->{throw new IllegalStateException("fixture");};
  PresenceStateStore.Listener observer=(j,s)->{if(j.isEmpty()){if(s.known||s.online||s.changedAtMillis!=0)throw new AssertionError("global signal");signals.incrementAndGet();}};
  PresenceStateStore.addListener(broken);PresenceStateStore.addListener(observer);
  PresenceStateStore.invalidateAll();
  check(PresenceStateStore.stateCount()==0&&signals.get()==1,"global reset isolates observers and clears all state");
  PresenceStateStore.invalidateAll();check(signals.get()==1,"empty reset is idempotent");
  PresenceStateStore.removeListener(broken);PresenceStateStore.removeListener(observer);
  PresenceStateStore.invalidate(null);PresenceStateStore.invalidate("");PresenceStateStore.invalidate("900@g.us");
  check(PresenceStateStore.stateCount()==0,"invalid or group identity ignored");
  check(PresenceStateStore.getLatest(null)==null,"null identity collection");
  check(PresenceStateStore.getLatest(Arrays.asList(null,"missing@lid"))==null,"missing identities");
  ExecutorService pool=Executors.newFixedThreadPool(6);List<Future<?>>tasks=new ArrayList<>();
  AtomicInteger observations=new AtomicInteger();
  for(int thread=0;thread<6;thread++){final int t=thread;tasks.add(pool.submit(()->{
   for(int i=0;i<2000;i++){String key="t"+t+"_"+(i%700)+"@lid";
    if(i%37==0)PresenceStateStore.invalidateAll();else if(i%3==0)PresenceStateStore.invalidate(key);else PresenceStateStore.update(key,(i&1)==0);
    PresenceStateStore.getLatest(Arrays.asList(key,pn));observations.incrementAndGet();
   }
  }));}
  for(Future<?>f:tasks)f.get(30,TimeUnit.SECONDS);pool.shutdown();
  check(observations.get()==12000,"all concurrent operations completed");
  check(PresenceStateStore.stateCount()<=2048,"concurrent cache bound");
  PresenceStateStore.invalidateAll();check(PresenceStateStore.stateCount()==0,"final reset remains empty");
  System.out.println("PASS: "+checks+" presence invalidation/cache checks; 12000 concurrent operations; no Android/transport claim");
 }
}
'''

def main():
    with tempfile.TemporaryDirectory(prefix='waex_presence_cache_') as td:
        p=Path(td)/'TestPresenceInvalidation.java';p.write_text(TEST)
        src=ROOT/'app/src/main/java/com/waenhancer/xposed/features/automation/PresenceStateStore.java'
        subprocess.run(['javac','--release','17','-d',td,str(src),str(p)],check=True,timeout=60)
        subprocess.run(['java','-cp',td,'com.waenhancer.xposed.features.automation.TestPresenceInvalidation'],check=True,timeout=60)
if __name__=='__main__':main()
