package com.waenhancer.utils

/** Evidence of a recent executing process, separate from settings and feature readiness. */
enum class InjectionEvidence(val label: String) {
    CURRENT("Injection confirmed"), MODULE_INACTIVE("Module inactive"),
    BOOT_UNKNOWN("Injection unconfirmed: boot identity unavailable"),
    PREVIOUS_BOOT("Injection unconfirmed: report from another boot"),
    NO_REPORT("Injection unconfirmed: no runtime report"),
    REPORT_EXPIRED("Injection unconfirmed: report expired or clock changed"),
    PROCESS_OBSERVATION_UNAVAILABLE("Injection unconfirmed: process check unavailable"),
    PROCESS_STOPPED("Reported process is not running"),
    PROCESS_CHANGED("Injection unconfirmed: process changed")
}

internal const val INJECTION_EVIDENCE_WINDOW_MS = 25_000L

internal fun isRecentTimestamp(recorded: Long, now: Long): Boolean =
    recorded >= 0L && now >= recorded && now - recorded <= INJECTION_EVIDENCE_WINDOW_MS

internal fun classifyInjection(
    isModuleActive: Boolean, recordedBoot: Int, currentBoot: Int, reportedPid: Int,
    runningPids: Set<Int>?, lastActiveTime: Long, now: Long
): InjectionEvidence = when {
    !isModuleActive -> InjectionEvidence.MODULE_INACTIVE
    currentBoot == -1 -> InjectionEvidence.BOOT_UNKNOWN
    reportedPid <= 0 || lastActiveTime <= 0L -> InjectionEvidence.NO_REPORT
    recordedBoot != currentBoot -> InjectionEvidence.PREVIOUS_BOOT
    !isRecentTimestamp(lastActiveTime, now) -> InjectionEvidence.REPORT_EXPIRED
    runningPids == null -> InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE
    runningPids.isEmpty() -> InjectionEvidence.PROCESS_STOPPED
    reportedPid !in runningPids -> InjectionEvidence.PROCESS_CHANGED
    else -> InjectionEvidence.CURRENT
}
