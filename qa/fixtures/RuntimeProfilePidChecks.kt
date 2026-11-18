package com.waenhancer.utils

/** Independent expected outcomes for the real process parser and injection classifier. */
private var checked = 0

private fun expect(name: String, expected: Any?, actual: Any?) {
    checked++
    if (expected != actual) throw AssertionError("$name: expected=$expected actual=$actual")
}

private fun expectImmutable(name: String, change: () -> Unit) {
    checked++
    try {
        change()
    } catch (_: UnsupportedOperationException) {
        return
    }
    throw AssertionError("$name: mutable collection exposed")
}

private fun injection(snapshot: XposedRuntimeSnapshot?, uid: Int?, reportedPid: Int): InjectionEvidence =
    classifyInjection(
        isModuleActive = true, recordedBoot = 12, currentBoot = 12,
        reportedPid = reportedPid, runningPids = snapshot?.pidsForUid("com.whatsapp", uid),
        lastActiveTime = 1L
    )

fun main() {
    val packageName = "com.whatsapp"
    val ownerUid = 10_197
    val workUid = 1_010_197
    val dual = parseProcessList(
        "UID PID NAME\n10197 123 com.whatsapp\n1010197 456 com.whatsapp\n1010191 789 com.waenhancer\n",
        observedAtElapsed = 4567L
    )
    expect("complete UID rows", true, dual.uidQualified)
    expect("real observation timestamp", 4567L, dual.observedAtElapsed)
    expect("owner process only", setOf(123), dual.pidsForUid(packageName, ownerUid))
    expect("work process only", setOf(456), dual.pidsForUid(packageName, workUid))
    expect("generic diagnostics still report both", setOf(123, 456), dual.pidsFor(packageName))
    expect("unknown UID cannot establish injection", emptySet<Int>(), dual.pidsForUid(packageName, 999_999))
    expect("missing installed package is stopped if observation exhaustive", emptySet<Int>(),
        dual.pidsForUid("com.whatsapp.w4b", workUid))
    expect("null expected UID", null, dual.pidsForUid(packageName, null))
    expect("invalid expected UID", null, dual.pidsForUid(packageName, -1))
    expect("owner report current", InjectionEvidence.CURRENT, injection(dual, ownerUid, 123))
    expect("work report current", InjectionEvidence.CURRENT, injection(dual, workUid, 456))
    expect("other-profile report rejected", InjectionEvidence.PROCESS_CHANGED, injection(dual, ownerUid, 456))

    val onlyWork = parseProcessList("1010197 123 com.whatsapp\n1010191 789 com.waenhancer\n")
    expect("other user running is not owner injection", InjectionEvidence.PROCESS_STOPPED,
        injection(onlyWork, ownerUid, 123))
    expect("same reused PID belongs to work", InjectionEvidence.CURRENT,
        injection(onlyWork, workUid, 123))
    expect("missing root observation is unknown", InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE,
        injection(null, ownerUid, 123))

    val oldPidOnly = parseProcessList("PID NAME\n123 com.whatsapp\n")
    expect("old PID-only format still readable for diagnostics", setOf(123), oldPidOnly.pidsFor(packageName))
    expect("old PID-only does not verify user", null, oldPidOnly.pidsForUid(packageName, ownerUid))
    expect("old PID-only is not current", InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE,
        injection(oldPidOnly, ownerUid, 123))
    val legacyUsername = parseProcessList("USER PID NAME\nu10_a197 123 com.whatsapp\n")
    expect("legacy USER string is not a numeric UID", null, legacyUsername.pidsForUid(packageName, workUid))
    val oldToolbox = parseProcessList("u10_a197 123 1 0 0 com.whatsapp\n")
    expect("old toolbox extended row retains name-only diagnostics", setOf(123), oldToolbox.pidsFor(packageName))
    expect("old toolbox never authorizes UID", null, oldToolbox.pidsForUid(packageName, workUid))
    val mixed = parseProcessList("1010197 123 com.whatsapp\nu10_a197 456 com.whatsapp\n")
    expect("mixed UID formats invalid", false, mixed.uidQualified)
    expect("mixed UID formats cannot confirm", null, mixed.pidsForUid(packageName, workUid))
    val badUid = parseProcessList("unknown 123 com.whatsapp\n")
    expect("malformed UID unknown", null, badUid.pidsForUid(packageName, ownerUid))
    val badPid = parseProcessList("10197 nope com.whatsapp\n")
    expect("malformed PID unknown", null, badPid.pidsForUid(packageName, ownerUid))
    val zeroPid = parseProcessList("10197 0 com.whatsapp\n")
    expect("zero PID unknown", null, zeroPid.pidsForUid(packageName, ownerUid))
    val blank = parseProcessList("UID PID NAME\n")
    expect("empty root response not authoritative", null, blank.pidsForUid(packageName, ownerUid))
    expect("incomplete snapshot cannot assert stopped", null,
        dual.copy(complete = false).pidsForUid(packageName, ownerUid))
    expect("partial snapshot cannot assert missing UID", null,
        dual.copy(exhaustive = false).pidsForUid("com.whatsapp.w4b", ownerUid))
    expect("duplicate numeric UID rows are merged", setOf(123, 124),
        parseProcessList("10197 123 com.whatsapp\n10197 124 com.whatsapp\n")
            .pidsForUid(packageName, ownerUid))
    expect("business target UID remains distinct", setOf(88),
        parseProcessList("1010198 88 com.whatsapp.w4b\n").pidsForUid("com.whatsapp.w4b", 1_010_198))
    expectImmutable("outer UID map") {
        @Suppress("UNCHECKED_CAST")
        (dual.runningPidsByUid as MutableMap<String, Map<Int, Set<Int>>>)["untrusted"] = emptyMap()
    }
    expectImmutable("inner UID map") {
        @Suppress("UNCHECKED_CAST")
        (dual.runningPidsByUid.getValue(packageName) as MutableMap<Int, Set<Int>>)[ownerUid] = emptySet()
    }
    expectImmutable("PID collection") {
        @Suppress("UNCHECKED_CAST")
        (dual.pidsForUid(packageName, workUid) as MutableSet<Int>).add(123)
    }
    println("PROFILE_PID_CASES=$checked;FAILURES=0")
}
