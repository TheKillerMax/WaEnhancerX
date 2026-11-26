package com.waenhancer.xposed.features.customization;

import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.ViewHookDispatcher;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.core.privacy.PrivacyPrefs;
import com.waenhancer.xposed.features.homescreen.ChatListCustomizationsHook;
import com.waenhancer.xposed.utils.ViewClassSelector;
import de.robv.android.xposed.XposedBridge;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Arrays;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class AppearanceCurrentContractTest {
    private Context context;
    private SharedPreferences prefs;
    private BaseFeature feature;
    public static final class Recommendation extends View {
        public Recommendation(Context context) { super(context); }
    }
    @Before public void setup() throws Exception {
        context = RuntimeEnvironment.getApplication();
        prefs = context.getSharedPreferences("appearance-current",0);
        prefs.edit().clear().commit(); XposedBridge.reset(); PrivacyPrefs.calls=0;
        // The fixture resets its Xposed engine between cases; reset the matching
        // public dispatcher registration state, without changing its behavior.
        Field flag=ViewHookDispatcher.class.getDeclaredField("flagsHooked");flag.setAccessible(true);flag.setBoolean(null,false);
        Field owners=ViewHookDispatcher.class.getDeclaredField("FLAGS");owners.setAccessible(true);((Map<?,?>)owners.get(null)).clear();
        DexSearchEngine.configuredClass=Recommendation.class;
    }
    @After public void cleanup() {
        if (feature != null) feature.unhookAll();
        assertEquals("No private/privacy initialization belongs to these view cases",0,PrivacyPrefs.calls);
        XposedBridge.reset();
    }
    private ChannelRecommendationsFilterHook channel() throws Throwable {
        ChannelRecommendationsFilterHook hook = new ChannelRecommendationsFilterHook(context,getClass().getClassLoader(),prefs);
        feature=hook; hook.beginHookTracking();
        try { hook.hook(); } finally { hook.endHookTracking(); }
        return hook;
    }
    private Recommendation construct() throws Throwable {
        Recommendation view=new Recommendation(context);
        view.setLayoutParams(new ViewGroup.MarginLayoutParams(140,75));
        ((ViewGroup.MarginLayoutParams)view.getLayoutParams()).setMargins(2,3,4,5);
        Constructor<?> constructor=Recommendation.class.getConstructor(Context.class);
        XposedBridge.fireAfter(XposedBridge.fireBefore(constructor,view,new Object[]{context}));
        return view;
    }
    private boolean chat(String method) throws Exception {
        if (feature == null) feature=new ChatListCustomizationsHook(context,getClass().getClassLoader(),prefs);
        Method m=ChatListCustomizationsHook.class.getDeclaredMethod(method);m.setAccessible(true);
        return (Boolean)m.invoke(feature);
    }
    private int flags(View view,int value,int mask) throws Throwable {
        Method setter=View.class.getDeclaredMethod("setFlags",int.class,int.class);
        return (Integer)XposedBridge.fireBefore(setter,view,new Object[]{value,mask}).args[0];
    }
    @Test public void channelHidesWithoutOverwritingHostLayout() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        Recommendation view=construct(); assertEquals(View.GONE,view.getVisibility());
        assertEquals(140,view.getLayoutParams().width);assertEquals(75,view.getLayoutParams().height);
        assertEquals(2,((ViewGroup.MarginLayoutParams)view.getLayoutParams()).leftMargin);
        assertEquals("waex_channel_rec_view_class_v2",DexSearchEngine.lastKey);
    }
    @Test public void channelHonorsLiveDisableAfterInstall() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        prefs.edit().putBoolean("channels_enhancements",false).commit();
        assertEquals(View.VISIBLE,construct().getVisibility());
    }
    @Test public void channelUsesCurrentTargetScopedSetting() throws Throwable {
        prefs.edit().putBoolean(context.getPackageName()+":channels_enhancements",true).commit();channel();
        assertEquals(View.GONE,construct().getVisibility());
    }
    @Test public void channelRejectsMissingContract() {
        prefs.edit().putBoolean("channels_enhancements",true).commit();DexSearchEngine.configuredClass=null;
        assertThrows(IllegalStateException.class,()->channel());
    }
    @Test public void channelRejectsNonViewCachedClass() {
        prefs.edit().putBoolean("channels_enhancements",true).commit();DexSearchEngine.configuredClass=String.class;
        assertThrows(IllegalStateException.class,()->channel());
    }
    @Test public void channelRegistrationUsesActualFeatureCleanup() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        Recommendation view=new Recommendation(context);
        assertEquals(View.GONE,flags(view,View.VISIBLE,12));feature.unhookAll();
        assertFalse(XposedBridge.hooks.containsKey(Recommendation.class.getConstructor(Context.class)));
        assertEquals("shared dispatcher has no retired owner rule",View.VISIBLE,flags(view,View.VISIBLE,12));
    }
    @Test public void channelHostRebindPreservesOtherFlagBits() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        assertEquals(0x02000000|View.GONE,flags(new Recommendation(context),0x02000000|View.INVISIBLE,12));
    }
    @Test public void channelRuleLeavesUnrelatedViewsAndMasksUntouched() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        assertEquals(View.VISIBLE,flags(new TextView(context),View.VISIBLE,12));
        assertEquals(0x02000000,flags(new Recommendation(context),0x02000000,0x02000000));
    }
    @Test public void channelHostRebindRespectsLiveDisable() throws Throwable {
        prefs.edit().putBoolean("channels_enhancements",true).commit();channel();
        prefs.edit().putBoolean("channels_enhancements",false).commit();
        assertEquals(View.VISIBLE,flags(new Recommendation(context),View.VISIBLE,12));
    }
    @Test public void chatMasterOffDoesNotBlockConversation() throws Exception {
        prefs.edit().putBoolean("metaai",false).commit();assertFalse(chat("shouldBlockAssistantChat"));
    }
    @Test public void chatMasterOffDoesNotRewriteHostConfiguration() throws Exception {
        prefs.edit().putBoolean("metaai",false).commit();assertFalse(chat("shouldDisableHostConfiguration"));
    }
    @Test public void chatTracksMasterDisableAfterInitialEnable() throws Exception {
        prefs.edit().putBoolean("metaai",true).commit();assertTrue(chat("shouldBlockAssistantChat"));
        prefs.edit().putBoolean("metaai",false).commit();assertFalse(chat("shouldBlockAssistantChat"));
    }
    @Test public void chatUsesScopedMasterAndExplicitRootOverride() throws Exception {
        prefs.edit().putBoolean(context.getPackageName()+":metaai",true).commit();assertTrue(chat("shouldBlockAssistantChat"));
        prefs.edit().putBoolean("metaai",false).commit();assertFalse(chat("shouldBlockAssistantChat"));
    }
    @Test public void conversationSelectorRequiresAViewGroup() {
        assertSame(FrameLayout.class,ViewClassSelector.uniqueViewGroup(Arrays.asList(TextView.class,FrameLayout.class)));
        assertNull(ViewClassSelector.uniqueViewGroup(Arrays.asList(TextView.class,String.class)));
    }
    @Test public void conversationSelectorRejectsMultipleGroups() {
        assertThrows(IllegalStateException.class,()->ViewClassSelector.uniqueViewGroup(Arrays.asList(ViewGroup.class,FrameLayout.class)));
    }
}
