package com.waenhancer.xposed.features.media;

import X.*;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import com.whatsapp.viewonce.ui.messaging.*;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.*;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.result.*;
import java.io.File;
import java.io.IOException;
import java.lang.ref.WeakReference;
import java.lang.reflect.*;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static com.waenhancer.xposed.features.media.ViewOnceDownloadTest.*;

public final class ViewOnceAudioTest {
    static Method created,createAudioMenu,prepareAudioMenu,selectedAudio,bindAudio;
    static DexKitBridge audioMetadata() throws Exception {
        DexKitBridge bridge=metadata();
        created=method(ViewOnceViewerActivity.class,"onCreate",Bundle.class);
        createAudioMenu=method(ViewOnceViewerActivity.class,"onCreateOptionsMenu",Menu.class);
        prepareAudioMenu=method(ViewOnceViewerActivity.class,"onPrepareOptionsMenu",Menu.class);
        selectedAudio=method(ViewOnceViewerActivity.class,"onOptionsItemSelected",MenuItem.class);
        bindAudio=method(ViewOnceAudioFragment.class,"bind",Bundle.class,View.class);
        calls(bridge,created,method(ActivitySupport.class,"getSupportFragmentManager"),
                method(Manager.class,"byTag",String.class),method(Manager.class,"byTag",String.class));
        MethodData optional=new MethodData(method(ActivitySupport.class,"getSupportFragmentManager"));
        optional.ownerOverride="com.whatsapp.optional.MissingActivity";optional.unavailable=true;
        data(bridge,created).calls.add(optional);
        data(bridge,created).strings.add("view_once_audio");data(bridge,created).strings.add("view_once_text");
        for(Method event:new Method[]{created,prepareAudioMenu,selectedAudio}) {
            reads(bridge,event,field(ViewOnceViewerActivity.class,"key"));
        }
        // A typed field read in only one event is not the Activity key contract.
        reads(bridge,created,field(ViewOnceViewerActivity.class,"backupKey"));
        data(bridge,bindAudio).strings.add("fMessage");
        reads(bridge,bindAudio,field(BaseViewOnceMessageViewerFragment.class,"message"));
        UsingFieldData optionalField=new UsingFieldData(field(BaseViewOnceMessageViewerFragment.class,"message"));
        optionalField.field.ownerOverride="com.whatsapp.optional.MissingHolder";optionalField.field.unavailable=true;
        data(bridge,bindAudio).fields.add(optionalField);
        data(bridge,method(ViewOnceAudioFragment.class,"decoyBind",Bundle.class,View.class));
        return bridge;
    }
    static ViewOnceAudioResolver audioContract(DexKitBridge bridge) throws Exception {
        return ViewOnceAudioResolver.discover(bridge,LOADER,contract(bridge));
    }
    static ViewOnceViewerActivity activity(Media message) {
        ViewOnceViewerActivity activity=new ViewOnceViewerActivity();activity.key=message.key;
        ViewOnceAudioFragment audio=new ViewOnceAudioFragment();audio.message=message;activity.manager.audio=audio;
        return activity;
    }
    static Media voice(File file,String jid,String id,boolean own) {
        return new Audio(new Key(new Chat(jid),id,own),new Data(file==null?null:file.getPath()));
    }
    static void invalidAudio(String label,java.util.function.Consumer<DexKitBridge> mutate) throws Exception {
        DexKitBridge bridge=audioMetadata();mutate.accept(bridge);boolean rejected=false;
        try{audioContract(bridge);}catch(IllegalArgumentException expected){rejected=true;}
        check("Reject audio contract: "+label,rejected);
    }
    static void callback(Method method,ViewOnceViewerActivity activity,MenuDouble menu,Object result,Throwable error) throws Throwable {
        XC_MethodHook hook=XposedBridge.hooks.get(method);check("Audio callback installed",hook!=null);
        XC_MethodHook.MethodHookParam p=new XC_MethodHook.MethodHookParam();p.thisObject=activity;p.args=new Object[]{menu};p.result=result;p.failure=error;
        hook.runAfter(p);check("Audio callback preserves result/exception/arguments",p.result==result&&p.failure==error&&p.args[0]==menu);
    }
    static void selection() throws Exception {
        ViewOnceAudioResolver resolver=audioContract(audioMetadata());
        File desired=file("voice"),other=file("other");
        Media message=voice(desired,"123@lid","id",false);
        ViewOnceViewerActivity activity=activity(message);
        check("Loaded audio identified without File lookup",resolver.hasAudio(activity)&&message.data.calls==0);
        check("Exact audio fragment tag",activity.manager.requested.equals("view_once_audio"));
        check("Loaded audio resolves canonical path",desired.equals(resolver.fileAtActivity(activity))&&message.data.calls==1);
        check("Null Activity",resolver.fileAtActivity(null)==null);
        check("Wrong Activity",resolver.fileAtActivity(new android.app.Activity())==null);
        activity.manager.audio=new ViewOnceTextFragment();
        ((ViewOnceTextFragment)activity.manager.audio).message=message;
        check("Text does not get audio export",!resolver.hasAudio(activity)&&resolver.fileAtActivity(activity)==null);
        activity.manager.audio=null;check("Fragment not committed",!resolver.hasAudio(activity));
        activity.manager=null;check("No fragment manager",!resolver.hasAudio(activity));
        for(String mismatch:new String[]{"jid","id","own","nullkey","nullmessage","notmedia"}) {
            ViewOnceViewerActivity changed=activity(message);
            changed.key=new Key(new Chat(mismatch.equals("jid")?"123@s.whatsapp.net":"123@lid"),
                    mismatch.equals("id")?"other":"id",mismatch.equals("own"));
            if(mismatch.equals("nullkey"))changed.key=null;
            if(mismatch.equals("nullmessage"))((ViewOnceAudioFragment)changed.manager.audio).message=null;
            if(mismatch.equals("notmedia"))((ViewOnceAudioFragment)changed.manager.audio).message=new Message(message.key);
            check("Audio identity mismatch: "+mismatch,!resolver.hasAudio(changed)&&resolver.fileAtActivity(changed)==null);
        }
        for(String change:new String[]{"jid","id","own","fragment","message","data"}) {
            Media audio=voice(desired,"123@lid","id",false);
            ViewOnceViewerActivity changing=activity(audio);
            audio.data.during=()->{
                switch(change){
                    case "fragment":changing.manager.audio=new ViewOnceAudioFragment();break;
                    case "message":((ViewOnceAudioFragment)changing.manager.audio).message=voice(other,"123@lid","id",false);break;
                    case "data":audio.data=new Data(other.getPath());break;
                    default:changing.key=new Key(new Chat(change.equals("jid")?"123@s.whatsapp.net":"123@lid"),
                            change.equals("id")?"other":"id",change.equals("own"));
                }
            };
            check("Audio selection changes during File accessor: "+change,resolver.fileAtActivity(changing)==null);
        }
        ViewOnceViewerActivity copied=activity(message);copied.key=new Key(new Chat("123@lid"),"id",false);
        check("Equal complete key accepted independently of object identity",desired.equals(resolver.fileAtActivity(copied)));
        invalidAudio("missing tag anchor",b->data(b,created).strings.clear());
        invalidAudio("missing manager edge",b->data(b,created).calls.removeIf(c->c.getName().equals("getSupportFragmentManager")));
        invalidAudio("missing tag lookup",b->data(b,created).calls.removeIf(c->c.getName().equals("byTag")));
        invalidAudio("ambiguous tag lookup",b->{try{calls(b,created,method(Manager.class,"decoyTag",String.class));}catch(Exception e){throw new AssertionError(e);}});
        invalidAudio("key not common to all host events",b->data(b,selectedAudio).fields.clear());
        invalidAudio("ambiguous common keys",b->{try{reads(b,prepareAudioMenu,field(ViewOnceViewerActivity.class,"backupKey"));reads(b,selectedAudio,field(ViewOnceViewerActivity.class,"backupKey"));}catch(Exception e){throw new AssertionError(e);}});
        invalidAudio("binding anchor missing",b->data(b,bindAudio).strings.clear());
        invalidAudio("message field absent",b->data(b,bindAudio).fields.clear());
        invalidAudio("message only written",b->data(b,bindAudio).fields.get(0).type=FieldUsingType.Write);
        invalidAudio("ambiguous message fields",b->{try{reads(b,bindAudio,field(BaseViewOnceMessageViewerFragment.class,"decoy"));}catch(Exception e){throw new AssertionError(e);}});
        invalidAudio("ambiguous bind callback",b->{try{
            Method second=method(ViewOnceAudioFragment.class,"decoyBind",Bundle.class,View.class);
            data(b,second).strings.add("fMessage");reads(b,second,field(BaseViewOnceMessageViewerFragment.class,"message"));
        }catch(Exception e){throw new AssertionError(e);}});
    }
    static void hooks() throws Throwable {
        DexSearchEngine.bridge=audioMetadata();Prefs prefs=new Prefs();
        DownloadViewOnceHook hook=new DownloadViewOnceHook(APP,LOADER,prefs);
        for(int failing:new int[]{3,4}) {
            XposedBridge.hooks.clear();XposedBridge.installs=0;XposedBridge.unhooks=0;XposedBridge.failAt=failing;
            hook.hook();
            check("Audio install failure preserves only complete photo/video pair "+failing,
                    XposedBridge.hooks.size()==2&&XposedBridge.hooks.containsKey(create)&&XposedBridge.hooks.containsKey(prepare)
                            &&XposedBridge.unhooks==failing-3);
        }
        XposedBridge.hooks.clear();XposedBridge.installs=0;XposedBridge.unhooks=0;XposedBridge.failAt=4;
        XposedBridge.fatal=new OutOfMemoryError("/private/fixture-secret-install");boolean propagated=false;
        try{hook.hook();}catch(OutOfMemoryError failure){propagated=failure==XposedBridge.fatal;}
        finally{XposedBridge.fatal=null;XposedBridge.failAt=0;}
        check("Audio fatal installation rolls back audio and propagates",propagated&&XposedBridge.hooks.size()==2&&XposedBridge.unhooks==1);
        XposedBridge.hooks.clear();XposedBridge.installs=0;hook.hook();
        check("Both verified photo/video and audio menu surfaces installed",XposedBridge.hooks.size()==4);
        File voice=file("voice");Media message=voice(voice,"chat@lid","a",false);ViewOnceViewerActivity activity=activity(message);
        MenuDouble menu=new MenuDouble();menu.add(0,19,0,"Host action");
        callback(createAudioMenu,activity,menu,true,null);check("Audio action present",menu.item()!=null);
        for(int i=0;i<100;i++)callback(prepareAudioMenu,activity,menu,true,null);
        check("Audio menu refresh performs no File lookup",message.data.calls==0);
        menu.item().click();idle();check("Audio uses explicit exporter route",GalleryMediaExporter.audioCopies==1&&GalleryMediaExporter.exported.equals(List.of(voice)));
        check("Audio export on worker",GalleryMediaExporter.thread.equals("WAEX-view-once-export"));
        Item stale=menu.item();activity.failure=new IllegalStateException("/private/fixture-secret-reflection");
        callback(prepareAudioMenu,activity,menu,true,null);
        check("Failed reflection after binding removes obsolete audio action",menu.item()==null&&menu.items.containsKey(19));
        stale.click();idle();check("Stale listener cannot export after reflection failure",GalleryMediaExporter.audioCopies==1);
        activity.failure=null;callback(prepareAudioMenu,activity,menu,true,null);
        Item retained=menu.item();prefs.enabled=false;callback(prepareAudioMenu,activity,menu,true,null);retained.click();
        check("Audio disabled removes only module action",menu.item()==null&&menu.items.containsKey(19)&&GalleryMediaExporter.audioCopies==1);
        prefs.enabled=true;callback(prepareAudioMenu,activity,menu,true,null);
        callback(prepareAudioMenu,activity,menu,false,null);check("Host false return respected",menu.item()==null);
        callback(createAudioMenu,activity,menu,true,null);
        callback(prepareAudioMenu,activity,menu,true,new IOException("private path"));check("Host exception removes optional action",menu.item()==null);
        callback(prepareAudioMenu,activity,menu,true,null);
        boolean weak=false;
        for(Field f:menu.item().listener.getClass().getDeclaredFields()){
            f.setAccessible(true);Object value=f.get(menu.item().listener);
            check("Audio listener does not capture Activity or menu",!(value instanceof android.app.Activity)&&!(value instanceof Menu));
            if(value instanceof WeakReference<?>){((WeakReference<?>)value).clear();weak=true;}
        }
        check("Audio listener has a weak Activity",weak);menu.item().click();idle();check("Collected audio Activity does not export",GalleryMediaExporter.audioCopies==1);
        callback(prepareAudioMenu,activity,menu,true,null);
        GalleryMediaExporter.entered=new CountDownLatch(1);GalleryMediaExporter.release=new CountDownLatch(1);menu.item().click();
        check("Audio copy enters controlled worker",GalleryMediaExporter.entered.await(2,TimeUnit.SECONDS));
        for(int i=0;i<100;i++)menu.item().click();check("Audio rapid taps cannot add copies",worker().getQueue().isEmpty());
        GalleryMediaExporter.release.countDown();idle();GalleryMediaExporter.entered=null;GalleryMediaExporter.release=null;
        check("Only one audio copy accepted",GalleryMediaExporter.audioCopies==2);
        GalleryMediaExporter.fail=true;menu.item().click();idle();GalleryMediaExporter.fail=false;
        check("Audio copy failure is not success",GalleryMediaExporter.audioCopies==2);
        check("Audio failures contain no sensitive payload",XposedBridge.logs.stream().noneMatch(s->s.contains("fixture-secret"))
                &&android.widget.Toast.shown.stream().noneMatch(s->s.contains("fixture-secret")));
        menu.item().click();idle();check("Audio retry after error",GalleryMediaExporter.audioCopies==3);
        activity.manager.audio=new ViewOnceTextFragment();callback(prepareAudioMenu,activity,menu,true,null);
        check("Text fragment never receives audio action",menu.item()==null);
        worker().shutdownNow();
    }
    static void baseline() throws Throwable {
        DexSearchEngine.bridge=audioMetadata();
        DownloadViewOnceHook hook=new DownloadViewOnceHook(APP,LOADER,new Prefs());hook.hook();
        File voice=file("voice");ViewOnceViewerActivity activity=activity(voice(voice,"chat@lid","a",false));
        MenuDouble menu=new MenuDouble();
        if(XposedBridge.hooks.containsKey(createAudioMenu))callback(createAudioMenu,activity,menu,true,null);
        check("Loaded view-once audio must expose an explicit export action",menu.item()!=null);
        menu.item().click();idle();check("Audio action delivers the selected file",GalleryMediaExporter.audioCopies==1);
        worker().shutdownNow();
    }
    public static void main(String[] args) throws Throwable {
        if(args.length>1&&args[1].equals("baseline"))baseline();else{selection();hooks();}
        System.out.println("PASS: "+checks+" audio contract, identity, menu and delivery checks (explicit doubles)");
    }
}
