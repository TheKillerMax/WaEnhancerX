package com.waenhancer.utils

import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInfo
import android.os.Process
import com.waenhancer.xposed.utils.AppRestartHelper
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowProcess
import java.nio.file.Files
import java.nio.file.Path

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [24, 28, 34], manifest = Config.NONE)
class ProfileProcessProbeTest {
    private lateinit var context: Context
    private val manager = "com.waenhancer"
    private val target = "com.whatsapp"
    private var managerUid = 10_000
    private var targetUid = 10_123
    @Before fun setup() {
        context = scoped(0)
        ShadowProcess.setUid(managerUid)
        ShadowProcess.setPid(99)
        install(target,targetUid)
        AppRestartHelper.calls=0;AppRestartHelper.failure=null;AppRestartHelper.output=""
        LsposedScopeReader.calls=0
    }
    private fun scoped(user: Int, offset: Int = 0): Context {
        val base=RuntimeEnvironment.getApplication()
        val info=ApplicationInfo(base.applicationInfo).also { it.uid=user*100_000+10_000+offset;it.packageName=manager }
        return object: ContextWrapper(base) {
            override fun getApplicationInfo()=info
            override fun getPackageName()=manager
            override fun getApplicationContext(): Context=this
        }
    }
    private fun install(name: String, uid: Int) {
        shadowOf(context.packageManager).installPackage(PackageInfo().also {
            it.packageName=name;it.applicationInfo=ApplicationInfo().also { app -> app.packageName=name;app.uid=uid }
        })
    }
    private fun rows(vararg lines: String)= "WAEX_LSPOSED_DB_OK\nWAEX_PS_BEGIN\n"+
        (listOf("$managerUid ${Process.myPid()} $manager")+lines).joinToString("\n")+"\nWAEX_PS_END\n"
    private fun probe(output: String): XposedRuntimeSnapshot? {
        AppRestartHelper.output=output
        return RootProbe.run(context).runtime
    }
    @Test fun acceptsExactUidAndManagerPid() {
        val result=probe(rows("$targetUid 4242 $target"))!!
        assertEquals(setOf(4242),result.pidsFor(target));assertFalse(result.exhaustive)
        assertEquals(1,AppRestartHelper.calls);assertEquals(1,LsposedScopeReader.calls)
    }
    @Test fun anotherProfileCannotSupplyTargetPresence() {
        assertEquals(emptySet<Int>(),probe(rows("1010123 4242 $target"))!!.pidsFor(target))
    }
    @Test fun sameProfileWrongPackageUidCannotSupplyPresence() {
        assertEquals(emptySet<Int>(),probe(rows("10124 4242 $target"))!!.pidsFor(target))
    }
    @Test fun selectsOnlyInitiatingWorkProfile() {
        context=scoped(10);managerUid=1_010_000;targetUid=1_010_123;ShadowProcess.setUid(managerUid);install(target,targetUid)
        assertEquals(setOf(44),probe(rows("10123 33 $target","$targetUid 44 $target"))!!.pidsFor(target))
    }
    @Test fun legacyBionicUidNameIdentifiesWorkProfile() {
        context=scoped(10);managerUid=1_010_000;targetUid=1_010_123;ShadowProcess.setUid(managerUid);install(target,targetUid)
        assertEquals(setOf(44),probe(rows("u10_a123 44 1 0 0 S $target","u0_a123 55 1 0 0 S $target"))!!.pidsFor(target))
    }
    @Test fun managerOnlyCanProveKnownTargetAbsence() {
        assertEquals(emptySet<Int>(),probe(rows())!!.pidsFor(target))
    }
    @Test fun missingPackageUidRemainsUnknown() {
        assertNull(probe(rows())!!.pidsFor("com.whatsapp.w4b"))
    }
    @Test fun anotherManagerProcessCannotProveCompletion() {
        assertNull(probe("WAEX_PS_BEGIN\n$managerUid ${Process.myPid()+1} $manager\nWAEX_PS_END"))
    }
    @Test fun anotherManagerProfileCannotProveCompletion() {
        assertNull(probe("WAEX_PS_BEGIN\n1010000 ${Process.myPid()} $manager\nWAEX_PS_END"))
    }
    @Test fun targetWithoutManagerCannotProveCompletion() {
        assertNull(probe("WAEX_PS_BEGIN\n$targetUid 33 $target\nWAEX_PS_END"))
    }
    @Test fun partialAndDuplicateMarkerResultsStayUnavailable() {
        for (output in listOf("",rows().replace("WAEX_PS_END",""),rows()+"WAEX_PS_END\n","noiseWAEX_PS_BEGIN\n$managerUid ${Process.myPid()} $manager\nWAEX_PS_END")) assertNull(probe(output))
    }
    @Test fun uidlessOrMalformedRowsCannotProveAbsence() {
        for (line in listOf("44 $target","??? 44 $target","$targetUid -1 $target","$targetUid invalid $target","2147483648 44 $target","u999999999999_a1 44 $target","u0_a999999 44 $target")) assertNull(probe(rows(line)))
    }
    @Test fun duplicatePidWithConflictingIdentityIsUnavailable() {
        assertNull(probe(rows("$targetUid 44 $target","1010123 44 $target")))
    }
    @Test fun repeatedIdenticalProcessRowsDeduplicate() {
        assertEquals(setOf(44),probe(rows("$targetUid 44 $target","$targetUid 44 $target"))!!.pidsFor(target))
    }
    @Test fun snapshotCollectionsCannotBeMutated() {
        val result=probe(rows("$targetUid 44 $target"))!!
        assertThrows(UnsupportedOperationException::class.java) { (result.runningPids as MutableMap).clear() }
        assertThrows(UnsupportedOperationException::class.java) { (result.pidsFor(target) as MutableSet).clear() }
    }
    @Test fun mismatchedContextUserNeverRunsRoot() {
        context=scoped(10);assertNull(probe(rows()));assertEquals(0,AppRestartHelper.calls);assertEquals(0,LsposedScopeReader.calls)
    }
    @Test fun sameUserDifferentApplicationUidNeverRunsRoot() {
        context=scoped(0,1);assertNull(probe(rows()));assertEquals(0,AppRestartHelper.calls)
    }
    @Test fun packageManagerOtherUserEntryNeverRunsRoot() {
        install(target,1_010_123);assertNull(probe(rows()));assertEquals(0,AppRestartHelper.calls)
    }
    @Test fun unknownProcessUidNeverRunsRoot() {
        ShadowProcess.setUid(-1);assertNull(probe(rows()));assertEquals(0,AppRestartHelper.calls)
    }
    @Test fun expectedRootErrorsRemainUnavailable() {
        for (failure in listOf(RuntimeException("denied"),UnsatisfiedLinkError("missing"))) {
            AppRestartHelper.failure=failure;assertNull(RootProbe.run(context).runtime)
        }
    }
    @Test fun unconfiguredBoundaryAssertionIsNotHidden() {
        AppRestartHelper.failure=AssertionError("fixture boundary")
        assertThrows(AssertionError::class.java) { RootProbe.run(context) }
    }
    @Test fun commandRequestsUidAndKeepsExactTargetFilter() {
        val command=RootProbe.processListCommand()
        assertTrue(command.contains("UID,PID,NAME"));assertTrue(command.contains("com\\.whatsapp\\.w4b"))
        assertThrows(IllegalArgumentException::class.java) { RootProbe.processListCommand("bad';id") }
        System.getProperty("waex.commandfile")?.let { Files.writeString(Path.of(it),command) }
        probe(rows());assertTrue(AppRestartHelper.lastCommand.contains("&& echo WAEX_PS_END"))
    }
}
