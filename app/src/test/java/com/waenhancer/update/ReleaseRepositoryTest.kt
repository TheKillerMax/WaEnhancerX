package com.waenhancer.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseRepositoryTest {
    private fun release(tag: String) = WaexRelease(tag, tag, "", "", "")

    @Test
    fun newerVersionOutranksOlderVersion() {
        assertTrue(ReleaseRepository.versionCode("3.2.1") > ReleaseRepository.versionCode("3.2.0"))
        assertTrue(ReleaseRepository.versionCode("3.3.0") > ReleaseRepository.versionCode("3.2.9"))
        assertTrue(ReleaseRepository.versionCode("4.0.0") > ReleaseRepository.versionCode("3.99.99"))
        assertTrue(ReleaseRepository.versionCode("1.6.9-beta-9") > ReleaseRepository.versionCode("1.6.9-beta-8"))
        assertTrue(ReleaseRepository.versionCode("1.6.9") > ReleaseRepository.versionCode("1.6.9-beta-9"))
    }

    @Test
    fun selectsNewestEligibleBuild() {
        val releases = listOf(release("1.6.8"), release("1.6.9-beta-9"), release("1.6.9"))
        assertEquals("1.6.9", ReleaseRepository.findUpdate(releases, "1.6.8")?.tagName)
        assertEquals("1.6.9", ReleaseRepository.findUpdate(releases, "1.6.9-beta-9")?.tagName)
    }

    @Test
    fun sameOrOlderBuildIsNotAnUpdate() {
        assertNull(ReleaseRepository.findUpdate(listOf(release("v3.2.0")), "3.2.0+42"))
        assertNull(ReleaseRepository.findUpdate(listOf(release("v3.1.0")), "3.2.0"))
    }
}
