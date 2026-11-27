#!/usr/bin/env python3
"""Compile the exact fallback-setting callback and verify acknowledged UI state.

Preference writes, Toast and resources are explicit JVM doubles. This does not
render Compose or establish Android persistence; the framework audio suite
executes the real preference manager and codec separately.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / 'app/src/main/java/com/waenhancer/ui/screens/calls/CallsHubScreen.kt'


def callback(source):
    matches = list(re.finditer(
        r'checked = allowMicrophoneFallback,\s+onCheckedChange = ', source))
    if len(matches) != 1:
        raise AssertionError('Expected one microphone-fallback callback')
    start = source.index('{', matches[0].end())
    depth = 0
    for end in range(start, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[start:end + 1]
    raise AssertionError('Unterminated fallback callback')


HARNESS = r'''
class PreferenceManager(val accepted: Boolean) {
    var writes = 0
    var values: Map<String, Boolean>? = null
    fun putBooleans(value: Map<String, Boolean>): Boolean {
        check(value.keys == setOf("call_recording_allow_mic_fallback"))
        writes++
        values = value
        return accepted
    }
}
object R { object string { const val call_recording_setting_save_failed = 1 } }
object UiText { fun get(id: Int, fallback: String): String = fallback }
class Toast {
    fun show() { shown++ }
    companion object {
        const val LENGTH_SHORT = 0
        var shown = 0
        fun makeText(context: Any, message: String, length: Int): Toast = Toast()
    }
}
fun main() {
    var checks = 0
    for (initial in listOf(false, true)) {
        for (requested in listOf(!initial, initial)) {
            for (accepted in listOf(false, true)) {
                val context = Any()
                val prefManager = PreferenceManager(accepted)
                var allowMicrophoneFallback = initial
                Toast.shown = 0
                val update: (Boolean) -> Unit = __CALLBACK__
                update(requested)
                check(allowMicrophoneFallback == if (accepted) requested else initial) {
                    "UI acknowledged a failed preference write"
                }; checks++
                check(Toast.shown == if (accepted) 0 else 1); checks++
                check(prefManager.writes == 1); checks++
                check(prefManager.values == mapOf("call_recording_allow_mic_fallback" to requested)); checks++
            }
        }
    }
    println("PASS: $checks checks across 8 acknowledged-write cases; extracted production callback")
}
'''


def execute(body, directory):
    implementation = directory / 'Checks.kt'
    implementation.write_text(HARNESS.replace('__CALLBACK__', body), encoding='utf-8')
    compiler = shutil.which('kotlinc.bat' if os.name == 'nt' else 'kotlinc')
    if not compiler:
        raise RuntimeError('Kotlin compiler is required')
    subprocess.run([compiler, '-jvm-target', '17', str(implementation),
                    '-include-runtime', '-d', str(directory / 'checks.jar')],
                   check=True, capture_output=True, text=True, timeout=90)
    return subprocess.run(['java', '-jar', str(directory / 'checks.jar')],
                          capture_output=True, text=True, timeout=30)


def main():
    body = callback(SCREEN.read_text(encoding='utf-8'))
    anchor = 'prefManager.putBooleans(mapOf("call_recording_allow_mic_fallback" to enabled))'
    if body.count(anchor) != 1:
        raise AssertionError('Expected the acknowledged Boolean preference write')
    with tempfile.TemporaryDirectory(prefix='waex_recording_setting_') as temp:
        root = Path(temp)
        good = root / 'good'; good.mkdir()
        healthy = execute(body, good)
        print(healthy.stdout, end='')
        healthy.check_returncode()
        bad = root / 'bad'; bad.mkdir()
        mutant = execute(body.replace(anchor, anchor + ' || true'), bad)
        if mutant.returncode == 0 or 'UI acknowledged a failed preference write' not in mutant.stderr:
            raise AssertionError('The compiled unconditional-acknowledgment control was not rejected')
    print('PASS: compiled unconditional UI acknowledgment rejected; no Compose or device claim')


if __name__ == '__main__':
    main()
