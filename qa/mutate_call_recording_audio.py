#!/usr/bin/env python3
"""Compile three independent regressions; require actual JUnit assertion failures."""
import argparse, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = 'app/src/main/java/com/waenhancer/xposed/features/media/CallRecordingHook.java'
SCREEN = 'app/src/main/java/com/waenhancer/ui/screens/calls/CallsHubScreen.kt'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--deps', type=Path, required=True)
    p.add_argument('--sdk-jars', type=Path, required=True)
    p.add_argument('--dexkit', type=Path, required=True)
    a = p.parse_args(); root = a.root.resolve(); out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    variants = {
        'implicit-microphone': (HOOK, 'prefs.getBoolean("call_recording_allow_mic_fallback", false)', 'prefs.getBoolean("call_recording_allow_mic_fallback", true)'),
        'ignore-opt-in': (HOOK, 'preferCallAudio && !allowMicrophoneFallback', 'false'),
        'optimistic-ui': (SCREEN, 'if (prefManager.putBooleans(mapOf("call_recording_allow_mic_fallback" to enabled)))', 'if (prefManager.putBooleans(mapOf("call_recording_allow_mic_fallback" to enabled)) || true)'),
    }
    results = []
    for name, (relative, before, after) in variants.items():
        stage = out / name / 'root'; stage.mkdir(parents=True)
        shutil.copytree(root / 'app', stage / 'app')
        source = stage / relative; text = source.read_text()
        if text.count(before) != 1: raise RuntimeError('Mutation must match exactly once: ' + name)
        source.write_text(text.replace(before, after))
        result_dir = out / name / 'run'
        command = [sys.executable, str(ROOT / 'qa/android_call_recording_audio_test.py'),
                   '--source-root', str(stage), '--out', str(result_dir), '--deps', str(a.deps.resolve()),
                   '--sdk-jars', str(a.sdk_jars.resolve()), '--dexkit', str(a.dexkit.resolve()), '--allow-test-failure']
        run = subprocess.run(command, capture_output=True, text=True, timeout=180)
        (out / name / 'driver.log').write_text(run.stdout + run.stderr)
        log = (result_dir / 'junit.log').read_text() if (result_dir / 'junit.log').exists() else ''
        counts = re.search(r'Tests run: (\d+),\s+Failures: (\d+)', log)
        assertions = len(re.findall(r'(?m)^java\.lang\.AssertionError(?::|$)', log))
        accepted = run.returncode == 0 and counts is not None and int(counts[1]) == 81 and int(counts[2]) == assertions and assertions > 0
        results.append({'variant': name, 'driver_exit': run.returncode, 'tests': int(counts[1]) if counts else None,
                        'assertion_failures': assertions, 'accepted': accepted,
                        'mutated_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        print(results[-1], flush=True)
    summary = {'source_root': str(root), 'results': results, 'accepted': all(x['accepted'] for x in results),
               'scope': 'Controlled recorder sources and exact UI callback; no audio, OEM routing, DEX or private engine execution.'}
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not summary['accepted']: raise RuntimeError('Mutation did not reach the expected assertions')

if __name__ == '__main__': main()
