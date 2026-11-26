#!/usr/bin/env python3
"""Legacy CI entry point for the current on-demand observation contract.

Upstream removed RuntimeObservationClock in 1b029ec88d9c. Compile the actual
refresh/drain bodies instead of recreating the retired timer. Scope scheduling
and probe IO are explicit observable boundaries; no root/Android work runs here.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    assert source.count(signature) == 1, signature
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("Unterminated production method")


FIXTURE = r"""
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.ConcurrentLinkedQueue
import com.waenhancer.utils.InjectionEvidence
import com.waenhancer.utils.classifyInjection
class Context { val applicationContext: Context get() = this }
class Flow<T>(var value: T)
class Scheduled {
    val jobs = ConcurrentLinkedQueue<() -> Unit>()
    fun launch(block: () -> Unit) { jobs.add(block) }
    fun drain() { while (true) (jobs.poll() ?: return).invoke() }
}
class Observer {
    OWNERSHIP_STATE
    val scope = Scheduled()
    val _probeError = Flow<String?>(null)
    var calls = 0
    var active = 0
    var maxActive = 0
    var onProbe: (() -> Unit)? = null
    // Probe IO is outside this scheduler test; it must be explicitly configured.
    private fun refreshOnce(context: Context) {
        val body = onProbe ?: throw AssertionError("probe boundary not configured")
        calls++
        active++
        maxActive = maxOf(maxActive, active)
        try { body() } finally { active-- }
    }
    REFRESH
    DRAIN
}
var checks = 0
fun ck(value: Boolean, message: String) { checks++; check(value) { message } }
fun main() {
    val context = Context()
    val idle = Observer()
    ck(idle.calls == 0 && idle.scope.jobs.isEmpty(), "construction started a periodic probe")
    idle.refresh(context)
    ck(idle.calls == 0, "refresh must use the scheduler boundary")
    var rejected = false
    try { idle.scope.drain() } catch (_: AssertionError) { rejected = true }
    ck(rejected, "unconfigured probe boundary must fail closed")
    idle.onProbe = {}
    idle.refresh(context); idle.scope.drain()
    ck(idle.calls == 1, "failed boundary wedged the drain ownership flag")

    val batched = Observer().apply { onProbe = {} }
    repeat(1000) { batched.refresh(context) }
    batched.scope.drain()
    ck(batched.calls == 1, "requests pending before a run must coalesce")
    ck(batched.maxActive == 1, "coalesced probes overlapped")
    batched.scope.drain()
    ck(batched.calls == 1, "idle scheduler invented another refresh")

    val concurrent = Observer()
    concurrent.onProbe = {
        if (concurrent.calls == 1) {
            repeat(100) { concurrent.refresh(context) }
            // A queued drain racing with the current owner must not start a probe.
            concurrent.scope.jobs.poll()!!.invoke()
        }
    }
    concurrent.refresh(context); concurrent.scope.drain()
    ck(concurrent.calls == 2, "request during a probe was lost or multiplied")
    ck(concurrent.maxActive == 1, "a second drain overlapped the probe")

    val failed = Observer().apply { onProbe = { throw IllegalStateException("fixture IO") } }
    failed.refresh(context); failed.scope.drain()
    ck(failed._probeError.value == "Refresh failed: IllegalStateException",
       "probe failure must surface its class without secret message")
    failed.onProbe = {}
    failed.refresh(context); failed.scope.drain()
    ck(failed.calls == 2 && failed.maxActive == 1, "exception blocked later refresh")
    fun evidence(pids: Set<Int>? = setOf(123), timestamp: Long = 1L,
                 active: Boolean = true, boot: Int = 7, recorded: Int = 7, pid: Int = 123) =
        classifyInjection(active, recorded, boot, pid, pids, timestamp)
    ck(evidence() == InjectionEvidence.CURRENT, "current boot/PID must not expire by report age")
    ck(evidence(timestamp = Long.MAX_VALUE) == InjectionEvidence.CURRENT,
       "clock changes must not invalidate current boot/PID proof")
    ck(evidence(active = false) == InjectionEvidence.MODULE_INACTIVE, "inactive module")
    ck(evidence(boot = -1) == InjectionEvidence.BOOT_UNKNOWN, "unknown boot")
    ck(evidence(recorded = 6) == InjectionEvidence.PREVIOUS_BOOT, "previous boot")
    ck(evidence(pid = 0) == InjectionEvidence.NO_REPORT, "missing PID report")
    ck(evidence(timestamp = 0) == InjectionEvidence.NO_REPORT, "missing timestamp report")
    ck(evidence(pids = null) == InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE, "unavailable process observation")
    ck(evidence(pids = emptySet()) == InjectionEvidence.PROCESS_STOPPED, "stopped process")
    ck(evidence(pids = setOf(456)) == InjectionEvidence.PROCESS_CHANGED, "restarted process")
    println("PASS: $checks current refresh/drain and boot/PID checks; 1100 coalesced requests, no Android/root")
}
"""


def replace_once(source, old, new):
    assert source.count(old) == 1, "Mutation anchor must match exactly once: " + old
    return source.replace(old, new, 1)


def retirement_contract(java):
    clock = java / "ui/components/RuntimeObservationClock.kt"
    assert not clock.exists(), "Retired observation clock reintroduced; review its scheduling contract"
    evidence = (java / "utils/InjectionEvidence.kt").read_text()
    assert "REPORT_EXPIRED" not in evidence and "isRecentTimestamp" not in evidence, "Retired heartbeat expiry reintroduced"
    health = (java / "ui/screens/settings/SystemHealthScreen.kt").read_text()
    assert "TargetAppManager.detectedApps.collectAsState()" in health, "Health UI must consume current target state"
    assert "rememberRuntimeObservationClock" not in health, "Health UI must not restore a periodic observation clock"
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    java = args.root / "app/src/main/java/com/waenhancer"
    manager_path = java / "utils/TargetAppManager.kt"
    manager = manager_path.read_text()
    evidence = retirement_contract(java)
    ownership = []
    for field in ("running", "rerunRequested"):
        declarations = re.findall(r"^    private val " + field + r" = AtomicBoolean\([^\n]+\)$", manager, re.MULTILINE)
        assert len(declarations) == 1, "Expected unique production ownership declaration: " + field
        ownership.extend(declarations)
    fixture = FIXTURE.replace("OWNERSHIP_STATE", "\n".join(ownership)).replace(
        "REFRESH", method(manager, "fun refresh(context: Context)")).replace(
        "DRAIN", method(manager, "private fun drain(context: Context)"))
    variants = [
        ("current", fixture, evidence, None),
        ("lost_request", replace_once(fixture, "rerunRequested.set(true)", "rerunRequested.set(false)"), evidence,
         "unconfigured probe boundary must fail closed"),
        ("lost_followup", replace_once(fixture,
            "try { refreshOnce(context) }", "try { refreshOnce(context); rerunRequested.set(false) }"), evidence,
         "request during a probe was lost or multiplied"),
        ("overlapping_drain", replace_once(fixture,
            "if (!running.compareAndSet(false, true)) return", "if (false) return"), evidence,
         "a second drain overlapped the probe"),
        ("wedged_owner", replace_once(fixture, "running.set(false)", "running.set(true)"), evidence,
         "failed boundary wedged the drain ownership flag"),
        ("exposed_error_message", replace_once(fixture,
            '${e.javaClass.simpleName}', '${e.message}'), evidence,
         "probe failure must surface its class without secret message"),
        ("age_expiry", fixture, replace_once(evidence,
            "else -> InjectionEvidence.CURRENT", "lastActiveTime < 10L -> InjectionEvidence.NO_REPORT\n    else -> InjectionEvidence.CURRENT"),
         "current boot/PID must not expire by report age"),
    ]
    result_rows = []
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="waex-observation-") as directory:
        temp = Path(directory)
        for name, candidate, candidate_evidence, expected in variants:
            path = temp / "ObservationChecks.kt"
            path.write_text(candidate, encoding="utf-8")
            evidence_path = temp / "InjectionEvidence.kt"
            evidence_path.write_text(candidate_evidence, encoding="utf-8")
            jar = temp / (name + ".jar")
            compiled = subprocess.run([shutil.which("kotlinc") or "kotlinc", "-nowarn",
                            "-language-version", "2.0", str(path), str(evidence_path), "-include-runtime", "-d", str(jar)],
                           text=True, capture_output=True, timeout=90)
            if args.out:
                (args.out / (name + "-compile.log")).write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
            assert compiled.returncode == 0, name + " failed to compile: " + compiled.stdout + compiled.stderr
            result = subprocess.run(["java", "-jar", str(jar)], text=True, capture_output=True, timeout=30)
            output = result.stdout + result.stderr
            if args.out:
                (args.out / (name + "-run.log")).write_text(output, encoding="utf-8")
            if expected is None:
                assert result.returncode == 0, output
                assert "PASS: 21 current refresh/drain and boot/PID checks" in output, output
                print(output, end="")
            else:
                assert result.returncode != 0 and expected in output, (name, output)
                print("PASS: compiled behavioral negative rejected " + name)
            result_rows.append({"variant": name, "compile_returncode": compiled.returncode,
                                "run_returncode": result.returncode, "expected_failure": expected,
                                "fixture_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                                "evidence_sha256": hashlib.sha256(candidate_evidence.encode()).hexdigest()})
    identities = {str(path.relative_to(args.root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        manager_path, java / "utils/InjectionEvidence.kt", java / "ui/screens/settings/SystemHealthScreen.kt")}
    if args.out:
        (args.out / "result.json").write_text(json.dumps({"checks": 21, "behavioral_mutants": 6,
            "production_sha256": identities, "variants": result_rows,
            "scope": "Actual refresh/drain methods, atomic ownership fields and InjectionEvidence; deterministic scheduler and probe IO boundaries; not Android, root or coroutine runtime"}, indent=2) + "\n", encoding="utf-8")
    print("PRODUCTION_SHA256=" + json.dumps(identities, sort_keys=True))


if __name__ == "__main__":
    main()
