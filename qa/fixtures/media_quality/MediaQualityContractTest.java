import android.content.Context;
import android.content.SharedPreferences;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.features.media.MediaQualityBypassHook;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.result.*;
import java.lang.reflect.*;
import java.util.*;

public final class MediaQualityContractTest {
    private static int checks, failed;
    private static final Context CONTEXT = new Context();
    private static final ClassLoader LOADER = MediaQualityContractTest.class.getClassLoader();

    static final class Preferences implements SharedPreferences {
        final Map<String, Boolean> values = new HashMap<>();
        @Override public boolean getBoolean(String k, boolean fallback) { return values.getOrDefault(k, fallback); }
        void put(String k, boolean enabled) { values.put(k, enabled); }
    }
    public static class Encoder {
        int quality;
        int fps = 30;
        Integer boxed = 30;
        boolean hd, fail;
        final RuntimeException failure = new IllegalStateException("fixture-private-media-value");
        public void image(int value) { quality = value; }
        public void otherImage(int value) { quality = value; }
        public void wrongImage(String value) {}
        public int frames() { if (fail) throw failure; return fps; }
        public Integer boxedFrames() { if (fail) throw failure; return boxed; }
        public int otherFrames() { return 24; }
        public boolean qualityTool() { if (fail) throw failure; return hd; }
        public boolean qualityToggle() { if (fail) throw failure; return hd; }
        public Boolean boxedToggle() { return Boolean.FALSE; }
    }

    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) { failed++; System.out.println("FAIL " + label); }
    }
    private static void expectUnavailable(BaseFeature hook, String label) {
        Throwable failure = null;
        try { hook.hook(); } catch (Throwable unavailable) { failure = unavailable; }
        check(failure instanceof IllegalStateException, label + "/missing contract is reported");
        check(failure != null && "Media quality contract unavailable".equals(failure.getMessage()),
                label + "/unavailable diagnostic is generic");
    }
    private static Method method(Class<?> c, String name, Class<?>... args) throws Exception {
        return c.getMethod(name, args);
    }
    private static MethodData metadata(DexKitBridge b, Class<?> c, String name, String anchor, Class<?>... args)
            throws Exception {
        MethodData value = new MethodData(method(c, name, args), anchor);
        b.methods.add(value);
        return value;
    }
    private static DexKitBridge reset() {
        XposedBridge.hooks.clear(); XposedBridge.logs.clear(); XposedBridge.rejected.clear();
        DexSearchEngine.initializes = 0; DexSearchEngine.failure = null;
        com.waenhancer.xposed.features.customization.PropsOverrideHook.BOOLEANS.clear();
        com.waenhancer.xposed.features.customization.PropsOverrideHook.INTEGERS.clear();
        MediaQualityBypassHook.configurePropertyOverrides(true);
        com.waenhancer.xposed.features.media.MediaHostFingerprint.accepted=true;
        DexKitBridge b = new DexKitBridge(); DexSearchEngine.bridge = b; return b;
    }
    private static void imageTests() throws Throwable {
        Preferences p = new Preferences(); p.put("imagequality", true);
        DexKitBridge b = reset(); metadata(b, Encoder.class, "image", "image/compress quality", int.class);
        new MediaQualityBypassHook(CONTEXT, LOADER, p).hook();
        Encoder encoder = new Encoder(); Method image = method(Encoder.class, "image", int.class);
        for (int quality : new int[]{75, 100}) {
            XposedBridge.invoke(image, encoder, quality);
            check(encoder.quality == 100, "media/image quality " + quality);
        }
        for (int sentinel : new int[]{0, -1, 101, Integer.MAX_VALUE}) {
            XposedBridge.invoke(image, encoder, sentinel);
            check(encoder.quality == sentinel, "media/preserve non-quality integer " + sentinel);
        }
        XC_MethodHook.MethodHookParam malformed = new XC_MethodHook.MethodHookParam(); malformed.args = null;
        try {
            for (XC_MethodHook callback : XposedBridge.hooks.getOrDefault(image, Collections.emptyList())) callback.before(malformed);
            check(true, "media/null argument envelope safe");
        } catch (NullPointerException failure) { check(false, "media/null argument envelope safe"); }
        p.put("imagequality", false); XposedBridge.invoke(image, encoder, 70);
        check(encoder.quality == 70, "media/image live disable");
        p.put("imagequality", true); XposedBridge.invoke(image, encoder, 70);
        check(encoder.quality == 100, "media/image live re-enable");

        b = reset(); metadata(b, Encoder.class, "image", "image/compress quality", int.class);
        metadata(b, Encoder.class, "otherImage", "image/compress quality", int.class);
        expectUnavailable(new MediaQualityBypassHook(CONTEXT, LOADER, p), "media/ambiguous image methods");
        check(XposedBridge.hooks.isEmpty(), "media/ambiguous image methods fail open");
    }
    private static void fpsTests() throws Throwable {
        Preferences p = new Preferences(); p.put("video_maxfps", true);
        DexKitBridge b = reset(); metadata(b, Encoder.class, "frames", "video/encoder fps");
        new MediaQualityBypassHook(CONTEXT, LOADER, p).hook();
        Encoder encoder = new Encoder(); Method frames = method(Encoder.class, "frames");
        check(Integer.valueOf(60).equals(XposedBridge.invoke(frames, encoder).getResult()), "media/valid FPS becomes 60");
        encoder.fps = 120;
        check(Integer.valueOf(120).equals(XposedBridge.invoke(frames, encoder).getResult()), "media/higher FPS not reduced");
        for (int value : new int[]{0, -1}) {
            encoder.fps = value;
            check(Integer.valueOf(value).equals(XposedBridge.invoke(frames, encoder).getResult()), "media/FPS sentinel " + value);
        }
        encoder.fail = true; XC_MethodHook.MethodHookParam failed = XposedBridge.invoke(frames, encoder);
        check(failed.getThrowable() == encoder.failure, "media/original codec exception preserved");
        encoder.fail = false; encoder.fps = 24; p.put("video_maxfps", false);
        check(Integer.valueOf(24).equals(XposedBridge.invoke(frames, encoder).getResult()), "media/FPS live disable");
        p.put("video_maxfps", true);
        check(Integer.valueOf(60).equals(XposedBridge.invoke(frames, encoder).getResult()), "media/FPS live re-enable");
        int scans = b.queries;
        for (int i = 0; i < 500; i++) XposedBridge.invoke(frames, encoder);
        check(b.queries == scans, "media/no DexKit scan from FPS callbacks");

        b = reset(); metadata(b, Encoder.class, "boxedFrames", "video/encoder fps");
        new MediaQualityBypassHook(CONTEXT, LOADER, p).hook(); encoder.boxed = null;
        check(XposedBridge.invoke(method(Encoder.class, "boxedFrames"), encoder).getResult() == null,
                "media/nullable FPS remains null");

        b = reset(); metadata(b, Encoder.class, "frames", "video/encoder fps");
        metadata(b, Encoder.class, "otherFrames", "video/encoder fps");
        expectUnavailable(new MediaQualityBypassHook(CONTEXT, LOADER, p), "media/ambiguous FPS methods");
        check(XposedBridge.hooks.isEmpty(), "media/ambiguous FPS methods fail open");
    }
    public static class Gallery extends androidx.fragment.app.Fragment {
        static final String FLAG="show_media_quality_toggle";
        boolean eligible=true, restricted, fail;
        final IllegalStateException failure=new IllegalStateException("private-flag-reader-error");
        public static boolean intentFlag(Gallery owner,String key,boolean fallback) {
            android.app.Activity activity=owner.getActivity();
            if(activity==null || activity.getIntent()==null)return fallback;
            android.content.Intent intent=activity.getIntent();
            return intent.hasExtra(key)?intent.getBooleanExtra(key,fallback):fallback;
        }
        public static boolean rawFlag(Gallery owner,String key,boolean fallback) {
            if(owner.fail)throw owner.failure;
            if(intentFlag(owner,key,fallback))return true;
            return owner.arguments!=null?owner.arguments.getBoolean(key,fallback):fallback;
        }
        public boolean eligibility() {
            // Explicit constructor-free simulation of the real host's raw call
            // through Xposed; the remainder is normal unmodified Java behavior.
            try {
                XC_MethodHook.MethodHookParam result=XposedBridge.invoke(
                        method(Gallery.class,"rawFlag",Gallery.class,String.class,boolean.class),
                        null,this,FLAG,false);
                if(result.hasThrowable())throw result.getThrowable();
                return Boolean.TRUE.equals(result.getResult()) && eligible && !restricted;
            } catch(RuntimeException|Error failure){throw failure;}
            catch(Throwable failure){throw new AssertionError(failure);}
        }
        public boolean otherEligibility(){return false;}
        public boolean unrelated(){return true;}
    }
    private static MethodData[] galleryFixture() throws Exception {
        DexKitBridge bridge=reset();
        MethodData predicate=metadata(bridge,Gallery.class,"eligibility",Gallery.FLAG);
        MethodData raw=metadata(bridge,Gallery.class,"rawFlag","",Gallery.class,String.class,boolean.class);
        MethodData intent=metadata(bridge,Gallery.class,"intentFlag","",Gallery.class,String.class,boolean.class);
        raw.anchors.clear();intent.anchors.clear();
        raw.opcodes.addAll(Arrays.asList(0x71,0x0a,0x39,0x54,0x38,0x6e,0x0a,0x12,0x38,0x12,0x0f));
        intent.opcodes.addAll(Arrays.asList(0x6e,0x0c,0x38,0x6e,0x0c,0x38,0x6e,0x0a,0x12,0x33,0x6e,0x0a,0x0f,0x0f));
        predicate.invokes.add(raw);
        raw.fields.add(new UsingFieldData(androidx.fragment.app.Fragment.class.getField("arguments")));
        raw.invokes.add(intent);
        raw.invokes.add(new MethodData(method(android.os.BaseBundle.class,"getBoolean",String.class,boolean.class)));
        intent.invokes.add(new MethodData(method(androidx.fragment.app.Fragment.class,"getActivity")));
        intent.invokes.add(new MethodData(method(android.app.Activity.class,"getIntent")));
        intent.invokes.add(new MethodData(method(android.content.Intent.class,"hasExtra",String.class)));
        intent.invokes.add(new MethodData(method(android.content.Intent.class,"getBooleanExtra",String.class,boolean.class)));
        return new MethodData[]{predicate,raw,intent};
    }
    private static void selectorTests() throws Throwable {
        Preferences prefs=new Preferences();MethodData[] data=galleryFixture();
        MediaQualityBypassHook hook=new MediaQualityBypassHook(CONTEXT,LOADER,prefs);hook.hook();
        Method raw=method(Gallery.class,"rawFlag",Gallery.class,String.class,boolean.class);
        Method predicate=method(Gallery.class,"eligibility");
        check(XposedBridge.hooks.containsKey(raw),"selector/raw reader installed");
        check(!XposedBridge.hooks.containsKey(predicate),"selector/aggregate predicate not hooked");
        check(XposedBridge.registrations()==1,"selector/only one callback");
        Gallery owner=new Gallery();
        check(!owner.eligibility(),"selector/off keeps absent UI flag");
        prefs.put("imagequality",true);
        check(owner.eligibility(),"selector/image-enabled raw flag available");
        owner.eligible=false;
        check(!owner.eligibility(),"selector/host eligibility denial preserved");
        owner.eligible=true;owner.restricted=true;
        check(!owner.eligibility(),"selector/host restriction preserved");
        owner.eligible=false;
        check(!owner.eligibility(),"selector/combined denial preserved");
        owner.eligible=true;owner.restricted=false;
        prefs.put("imagequality",false);prefs.put("video_maxfps",true);
        check(owner.eligibility(),"selector/video-only presentation flag");
        prefs.put("video_maxfps",false);
        check(!owner.eligibility(),"selector/live disable");
        prefs.put("imagequality",true);
        check(Boolean.FALSE.equals(XposedBridge.invoke(raw,null,owner,"another_flag",false).getResult()),"selector/unrelated false key unchanged");
        check(Boolean.TRUE.equals(XposedBridge.invoke(raw,null,owner,"another_flag",true).getResult()),"selector/unrelated true key unchanged");
        owner.fail=true;
        check(XposedBridge.invoke(raw,null,owner,Gallery.FLAG,false).getThrowable()==owner.failure,"selector/original error preserved");
        owner.fail=false;
        XC_MethodHook callback=XposedBridge.hooks.get(raw).get(0);
        XC_MethodHook.MethodHookParam malformed=new XC_MethodHook.MethodHookParam();
        malformed.args=null;malformed.setResult(false);callback.after(malformed);
        check(Boolean.FALSE.equals(malformed.getResult()),"selector/null args unchanged");
        malformed.args=new Object[]{new Object(),Gallery.FLAG,false};callback.after(malformed);
        check(Boolean.FALSE.equals(malformed.getResult()),"selector/foreign owner unchanged");
        malformed.args=new Object[]{owner,Gallery.FLAG,"notBoolean"};callback.after(malformed);
        check(Boolean.FALSE.equals(malformed.getResult()),"selector/malformed default unchanged");
        malformed.args=new Object[]{owner,Gallery.FLAG,false};malformed.setResult(null);callback.after(malformed);
        check(malformed.getResult()==null,"selector/null result unchanged");
        hook.hook();check(XposedBridge.registrations()==1,"selector/repeated installation unique");
        for(int variant=0;variant<7;variant++){
            data=galleryFixture();
            if(variant==0)data[1].opcodes.set(0,0x6e);
            if(variant==1)data[2].opcodes.add(0x12);
            if(variant==2)data[1].invokes.add(new MethodData(method(Gallery.class,"unrelated")));
            if(variant==3)data[2].invokes.remove(3);
            if(variant==4)data[1].fields.clear();
            if(variant==5)metadata(DexSearchEngine.bridge,Gallery.class,"otherEligibility",Gallery.FLAG);
            if(variant==6)data[1].anchors.add("unverified-condition");
            expectUnavailable(new MediaQualityBypassHook(CONTEXT,LOADER,prefs),"selector/unsupported shape "+variant);
            check(XposedBridge.registrations()==0,"selector/unsupported host untouched "+variant);
        }
        reset();metadata(DexSearchEngine.bridge,Encoder.class,"qualityTool","enable_media_quality_tool");
        expectUnavailable(new MediaQualityBypassHook(CONTEXT,LOADER,prefs),"selector/unverified legacy predicate");
        check(XposedBridge.registrations()==0,"selector/legacy aggregate result untouched");
        galleryFixture();XposedBridge.rejected.add(raw);
        expectUnavailable(new MediaQualityBypassHook(CONTEXT,LOADER,prefs),"selector/registration rejected");
        check(XposedBridge.registrations()==0,"selector/rejected registration not counted");
    }
    public static void main(String[] args) throws Throwable {
        imageTests(); fpsTests(); selectorTests();
        System.out.println("RESULT checks=" + checks + " failures=" + failed + " suite=media");
        if (failed != 0) throw new AssertionError(failed + " media-quality contract failures");
        System.out.println("PASS compiled production media-quality contract and explicit host/Xposed boundaries");
    }
}
