#!/usr/bin/env python3
"""Legacy CI entry point for the current on-demand observation contract.

Upstream removed RuntimeObservationClock in 1b029ec88d9c. Compile the actual
refresh/drain bodies instead of recreating the retired timer. Scope scheduling
and probe IO are explicit observable boundaries; no root/Android work runs here.
"""
from pathlib import Path
import argparse, hashlib, re, shutil, subprocess, tempfile

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
class Context { val applicationContext: Context get() = this }
class Flow<T>(var value: T)
class Scheduled {
    val jobs = ConcurrentLinkedQueue<() -> Unit>()
    fun launch(block: () -> Unit) { jobs.add(block) }
    fun drain() { while (true) (jobs.poll() ?: return).invoke() }
}
class Observer {
    private val running = AtomicBoolean(false)
    private val rerunRequested = AtomicBoolean(false)
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
    println("PASS: $checks actual on-demand refresh/drain checks; 1100 coalesced requests, no Android/root")
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    java = args.root / "app/src/main/java/com/waenhancer"
    manager_path = java / "utils/TargetAppManager.kt"
    manager = manager_path.read_text()
    assert not (java / "ui/components/RuntimeObservationClock.kt").exists()
    evidence = (java / "utils/InjectionEvidence.kt").read_text()
    assert "REPORT_EXPIRED" not in evidence and "isRecentTimestamp" not in evidence
    assert "TargetAppManager.detectedApps.collectAsState()" in (
        java / "ui/screens/settings/SystemHealthScreen.kt").read_text()
    fixture = FIXTURE.replace("REFRESH", method(manager, "fun refresh(context: Context)")).replace(
        "DRAIN", method(manager, "private fun drain(context: Context)"))
    variants = [
        ("current", fixture, None),
        ("lost_request", fixture.replace("rerunRequested.set(true)", "rerunRequested.set(false)", 1),
         "unconfigured probe boundary must fail closed"),
        ("lost_followup", fixture.replace(
            "try { refreshOnce(context) }",
            "try { refreshOnce(context); rerunRequested.set(false) }", 1),
         "request during a probe was lost or multiplied"),
    ]
    with tempfile.TemporaryDirectory(prefix="waex-observation-") as directory:
        temp = Path(directory)
        for name, candidate, expected in variants:
            path = temp / "ObservationChecks.kt"
            path.write_text(candidate, encoding="utf-8")
            jar = temp / (name + ".jar")
            subprocess.run([shutil.which("kotlinc") or "kotlinc", "-nowarn",
                            "-language-version", "2.0", str(path), "-include-runtime", "-d", str(jar)],
                           check=True, timeout=90)
            result = subprocess.run(["java", "-jar", str(jar)], text=True, capture_output=True, timeout=30)
            output = result.stdout + result.stderr
            if expected is None:
                assert result.returncode == 0, output
                print(output, end="")
            else:
                assert result.returncode != 0 and expected in output, (name, output)
                print("PASS: behavioral negative rejected " + name)
    print("PRODUCTION_SHA256=" + hashlib.sha256(manager_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
