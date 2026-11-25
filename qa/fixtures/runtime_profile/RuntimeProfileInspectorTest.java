package com.waenhancer.utils;

import android.app.Application;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.os.Process;
import android.os.SystemClock;
import com.waenhancer.xposed.utils.AppRestartHelper;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.LooperMode;
import org.robolectric.shadows.ShadowProcess;
import static org.junit.Assert.*;

/** Android framework identity APIs; explicit package/UID metadata and root output. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = "qa/fixtures/runtime_profile/AndroidManifest.xml")
@LooperMode(LooperMode.Mode.PAUSED)
public final class RuntimeProfileInspectorTest {
    private static final String TARGET = "com.whatsapp";
    private Application app;

    @Before public void setUp() {
        app = RuntimeEnvironment.getApplication();
        ShadowProcess.setUid(12345);
        ShadowProcess.setPid(1);
        app.getApplicationInfo().uid = Process.myUid();
        assertEquals(12345, app.getApplicationInfo().uid);
        assertEquals("com.waenhancer", app.getPackageName());
        installManager(Process.myUid());
        AppRestartHelper.reset();
    }

    private void installManager(int uid) {
        PackageInfo info = new PackageInfo();info.packageName = "com.waenhancer";
        info.applicationInfo = new ApplicationInfo();info.applicationInfo.packageName = info.packageName;
        info.applicationInfo.uid = uid;
        Shadows.shadowOf(app.getPackageManager()).installPackage(info);
    }

    private void installTarget(int uid) {
        PackageInfo info = new PackageInfo();
        info.packageName = TARGET;
        info.applicationInfo = new ApplicationInfo();
        info.applicationInfo.packageName = TARGET;
        info.applicationInfo.uid = uid;
        Shadows.shadowOf(app.getPackageManager()).installPackage(info);
    }

    private static String snapshot(int uid, String pids) {
        return "WAEX_PS_BEGIN\nPID|" + TARGET + "|" + uid + "|" + pids
                + "\nPID|com.waenhancer|" + Process.myUid() + "|1\nWAEX_PS_END\n";
    }

    private XposedRuntimeSnapshot inspect() {
        return RootProbe.INSTANCE.run(app).getRuntime();
    }

    private void assertUnavailableBeforeRoot() {
        assertNull(inspect());
        assertEquals("Rejected identity must not issue a root probe", 0, AppRestartHelper.calls);
    }

    @Test public void acceptsPrimaryProfileThroughFrameworkPackageManager() throws Exception {
        installTarget(23456);
        assertEquals(23456, app.getPackageManager().getApplicationInfo(TARGET, 0).uid);
        AppRestartHelper.output = snapshot(23456, "101 102");
        XposedRuntimeSnapshot result = inspect();
        assertNotNull(result);
        assertTrue(result.getComplete());
        assertEquals(Set.of(101, 102), result.pidsFor(TARGET));
        assertEquals(1, AppRestartHelper.calls);
        assertTrue(AppRestartHelper.lastCommand.contains("'23456'"));
    }

    @Test public void acceptsMatchingWorkProfileUid() {
        ShadowProcess.setUid(1012345);
        app.getApplicationInfo().uid = Process.myUid();
        installManager(Process.myUid());
        installTarget(1023456);
        AppRestartHelper.output = snapshot(1023456, "103");
        XposedRuntimeSnapshot result = inspect();
        assertNotNull(result);
        assertEquals(Set.of(103), result.pidsFor(TARGET));
        assertTrue(AppRestartHelper.lastCommand.contains("'1023456'"));
    }

    @Test public void rejectsContextFromAnotherUserBeforeRoot() {
        // Target and Context agree with one another; only the process-user guard rejects this.
        app.getApplicationInfo().uid = 1012345;
        installTarget(1023456);
        AppRestartHelper.output = snapshot(1023456, "103");
        assertEquals(12345, Process.myUid());
        assertUnavailableBeforeRoot();
    }

    @Test public void rejectsTargetFromAnotherUserBeforeRoot() {
        installTarget(1023456);
        AppRestartHelper.output = snapshot(1023456, "103");
        assertUnavailableBeforeRoot();
    }

    @Test public void rejectsNegativeContextUidBeforeRoot() {
        app.getApplicationInfo().uid = -1;
        installTarget(23456);
        AppRestartHelper.output = snapshot(23456, "101");
        assertUnavailableBeforeRoot();
    }

    @Test public void uninstalledTargetRemainsUnknownInsteadOfStopped() {
        AppRestartHelper.output = "WAEX_PS_BEGIN\nPID|com.waenhancer|12345|1\nWAEX_PS_END\n";
        XposedRuntimeSnapshot result = inspect();
        assertNotNull(result);
        assertNull(result.pidsFor(TARGET));
        assertFalse(AppRestartHelper.lastCommand.contains("pidof 'com.whatsapp'"));
    }

    @Test public void rejectsReturnedUidThatDoesNotMatchPackageMetadata() {
        installTarget(23456);
        AppRestartHelper.output = snapshot(1023456, "103");
        assertNull(inspect());
        assertEquals(1, AppRestartHelper.calls);
    }

    @Test public void completeEmptyPidRecordMeansNoProcess() {
        installTarget(23456);
        AppRestartHelper.output = snapshot(23456, "");
        XposedRuntimeSnapshot result = inspect();
        assertNotNull(result);
        assertEquals(Collections.emptySet(), result.pidsFor(TARGET));
    }

    @Test public void partialProbeCannotBecomeAnObservation() {
        installTarget(23456);
        AppRestartHelper.output = "PID|" + TARGET + "|23456|101\n";
        assertNull(inspect());
    }

    @Test public void unavailableProbeDoesNotReusePreviousFrameworkObservation() {
        installTarget(23456);
        AppRestartHelper.output = snapshot(23456, "101");
        assertNotNull(inspect());
        AppRestartHelper.failure = new SecurityException("controlled root denial");
        assertNull(inspect());
        assertEquals(2, AppRestartHelper.calls);
    }
    @Test public void anotherManagerPidCannotValidateTheObservation() {
        installTarget(23456);
        AppRestartHelper.output = snapshot(23456, "101").replace("|12345|1\n", "|12345|99\n");
        assertNull(inspect());
        assertEquals(1, AppRestartHelper.calls);
    }

    @Test public void anotherContextUidInSameProfileIsRejectedBeforeRoot() {
        installTarget(23456);
        app.getApplicationInfo().uid = 12346;
        assertUnavailableBeforeRoot();
    }

}
