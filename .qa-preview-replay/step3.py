from pathlib import Path
p=W/'qa/fixtures/media_preview/MediaPreviewLifecycleTest.java';s=p.read_text(encoding='utf-8')
extra=r'''
    private Object activeSession() throws Exception {
        Field f=MediaPreviewHook.class.getDeclaredField("activePreview");f.setAccessible(true);return f.get(hook);
    }
    private Method sessionMethod(String name,Class<?>...tail)throws Exception {
        Class<?>[] args=new Class<?>[tail.length+1];args[0]=Class.forName(MediaPreviewHook.class.getName()+"$PreviewSession");
        System.arraycopy(tail,0,args,1,tail.length);Method m=MediaPreviewHook.class.getDeclaredMethod(name,args);m.setAccessible(true);return m;
    }
    public static final class CountingProgress extends android.widget.ProgressBar {
        int writes;
        CountingProgress(Context c){super(c,null,android.R.attr.progressBarStyleHorizontal);writes=0;}
        @Override public synchronized void setProgress(int n){writes++;super.setProgress(n);}
    }
    @Test public void progressBurstCoalescesAndShowsLatestValue()throws Exception {
        open(null,"image/png",local(".png"));settle();Object session=activeSession();assertNotNull(session);
        CountingProgress progress=new CountingProgress(activity);android.widget.TextView text=new android.widget.TextView(activity);
        Method post=sessionMethod("postDownloadProgress",android.widget.ProgressBar.class,android.widget.TextView.class,int.class,String.class);
        for(int i=0;i<5000;i++)post.invoke(hook,session,progress,text,100+i,"size-"+i);
        assertEquals("Progress is queued, not applied on the worker",0,progress.writes);
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals("Underestimated size must not enqueue one UI callback per read",1,progress.writes);
        assertEquals(100,progress.getProgress());assertTrue(text.getText().toString().contains("size-4999"));
    }
    @Test public void progressCancellationDropsPendingUi()throws Exception {
        open(null,"image/png",local(".png"));settle();Object session=activeSession();
        CountingProgress progress=new CountingProgress(activity);android.widget.TextView text=new android.widget.TextView(activity);
        Method post=sessionMethod("postDownloadProgress",android.widget.ProgressBar.class,android.widget.TextView.class,int.class,String.class);
        post.invoke(hook,session,progress,text,101,"obsolete");latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals("Cancelled progress must not update old controls",0,progress.writes);
    }
    @Test public void pendingDecodedImageRecycledOnDismiss()throws Exception {
        open(null,"image/png",local(".png"));settle();Object session=activeSession();
        android.graphics.Bitmap bitmap=android.graphics.Bitmap.createBitmap(2,2,android.graphics.Bitmap.Config.ARGB_8888);
        Method post=sessionMethod("postDecodedImage",android.graphics.Bitmap.class,Context.class,android.widget.FrameLayout.class,android.widget.LinearLayout.class);
        android.widget.FrameLayout target=new android.widget.FrameLayout(activity);
        post.invoke(hook,session,bitmap,activity,target,new android.widget.LinearLayout(activity));
        assertFalse(bitmap.isRecycled());latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertTrue("Cancelled unpublished bitmap must be released",bitmap.isRecycled());assertEquals(0,target.getChildCount());
    }
    @Test public void alreadyCancelledDecodeResultIsRecycled()throws Exception {
        open(null,"image/png",local(".png"));settle();Object session=activeSession();latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        android.graphics.Bitmap bitmap=android.graphics.Bitmap.createBitmap(2,2,android.graphics.Bitmap.Config.ARGB_8888);
        sessionMethod("postDecodedImage",android.graphics.Bitmap.class,Context.class,android.widget.FrameLayout.class,android.widget.LinearLayout.class)
            .invoke(hook,session,bitmap,activity,new android.widget.FrameLayout(activity),new android.widget.LinearLayout(activity));
        assertTrue("Result decoded after cancellation must be released",bitmap.isRecycled());
    }
    @Test public void borrowedFileNamedLikeTemporaryRetainsBytes()throws Exception {
        File file=new File(activity.getCacheDir(),"mediapreview_host_owned.png");Files.write(file.toPath(),FixtureNetwork.PNG);
        byte[] original=Files.readAllBytes(file.toPath());open(null,"image/png",file);settle();
        latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertTrue(file.isFile());assertArrayEquals("A cache directory or prefix does not transfer ownership",original,Files.readAllBytes(file.toPath()));
    }
    @Test public void cancelledLateResponseClosesBody()throws Exception {
        FixtureNetwork.Scenario scenario=new FixtureNetwork.Scenario(true,false);scenario.ignoreCancellation=true;
        openBlocking("https://example.invalid/late-body",scenario);latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        scenario.release.countDown();settle();
        assertTrue("Response arriving after cancellation must still close its body",FixtureNetwork.calls.get(0).closed);
        assertTrue(previews().isEmpty());
    }
    @Test public void publicationWaitsForSessionCancellationMonitor()throws Exception {
        open(null,"image/png",local(".png"));settle();Object session=activeSession();
        Method post=sessionMethod("postPreview",kotlin.jvm.functions.Function0.class);
        CountDownLatch entered=new CountDownLatch(1);java.util.concurrent.atomic.AtomicReference<Throwable> error=new java.util.concurrent.atomic.AtomicReference<>();
        java.util.concurrent.atomic.AtomicInteger effects=new java.util.concurrent.atomic.AtomicInteger();
        Thread thread=new Thread(()->{entered.countDown();try{post.invoke(hook,session,(kotlin.jvm.functions.Function0<kotlin.Unit>)()->{effects.incrementAndGet();return kotlin.Unit.INSTANCE;});}catch(Throwable t){error.set(t);}});
        synchronized(session){thread.start();assertTrue(entered.await(2,TimeUnit.SECONDS));
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            while(thread.getState()!=Thread.State.BLOCKED&&thread.isAlive()&&System.nanoTime()<deadline)Thread.yield();
            assertEquals("Post registration must serialize with cancellation",Thread.State.BLOCKED,thread.getState());
            latest().dismiss();Shadows.shadowOf(Looper.getMainLooper()).idle();
        }
        thread.join(2000);assertFalse(thread.isAlive());assertNull(error.get());Shadows.shadowOf(Looper.getMainLooper()).idle();assertEquals(0,effects.get());
    }
'''
s=s.rstrip();assert s.endswith('}');s=s[:-1]+extra+'\n}\n';p.write_text(s,encoding='utf-8')
p=W/'qa/android_media_preview_test.py';s=p.read_text(encoding='utf-8').replace('EXPECTED_TESTS = 36','EXPECTED_TESTS = 57')
needle="    stubs['com/waenhancer/app/R.java']='package"
idx=s.index(needle)
s=s[:idx]+'''    import xml.etree.ElementTree as ET
    resource_ids=set()
    for resource_file in (root/'app/src/main/res/values').glob('*.xml'):
        tree=ET.parse(resource_file)
        resource_ids.update(e.attrib['name'] for e in tree.getroot() if e.tag=='string' and 'name' in e.attrib)
    missing=set(ids)-resource_ids
    if missing: raise RuntimeError('Preview refers to absent real resource identifiers: '+repr(sorted(missing)))
''' +s[idx:];p.write_text(s,encoding='utf-8')
