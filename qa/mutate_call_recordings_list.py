#!/usr/bin/env python3
"""Reject storage/ownership/metadata regressions through compiled Android assertions."""
import argparse, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = 'app/src/main/java/com/waenhancer/ui/screens/calls/CallsHubScreen.kt'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--deps', type=Path, required=True)
    p.add_argument('--sdk-jars', type=Path, required=True)
    p.add_argument('--core-jar', type=Path, required=True)
    a = p.parse_args(); root = a.root.resolve(); out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    variants = {
        'permission-hides-owned': [('if (selectedTab == "recordings") {\n            loadRecordings()', 'if (selectedTab == "recordings" && canReadLegacyRecordings) {\n            loadRecordings()')],
        'late-player-ownership': [('mediaPlayer = mp\n', ''), ('mp.start()\n', 'mp.start()\n                                            mediaPlayer = mp\n')],
        'metadata-false-success': [('onFailure { metadataFailed = true }', 'onFailure { metadataFailed = false }')],
        'cancel-as-failure': [('} catch (cancelled: CancellationException) {\n            throw cancelled\n', '')],
    }
    results = []
    for name, replacements in variants.items():
        stage = out / name / 'root'; stage.mkdir(parents=True)
        shutil.copytree(root / 'app', stage / 'app')
        source = stage / SCREEN; text = source.read_text()
        for before, after in replacements:
            if text.count(before) != 1: raise RuntimeError('Mutation must match exactly once: ' + name)
            text = text.replace(before, after)
        source.write_text(text)
        result_dir = out / name / 'run'
        command = [sys.executable, str(ROOT / 'qa/android_call_recordings_list_test.py'),
                   '--source-root', str(stage), '--out', str(result_dir), '--deps', str(a.deps.resolve()),
                   '--sdk-jars', str(a.sdk_jars.resolve()), '--core-jar', str(a.core_jar.resolve()), '--allow-test-failure']
        run = subprocess.run(command, capture_output=True, text=True, timeout=180)
        (out / name / 'driver.log').write_text(run.stdout + run.stderr)
        log = (result_dir / 'junit.log').read_text() if (result_dir / 'junit.log').exists() else ''
        counts = re.search(r'Tests run: (\d+),\s+Failures: (\d+)', log)
        assertions = len(re.findall(r'(?m)^(?:java\.lang\.AssertionError|org\.junit\.ComparisonFailure|org\.junit\.internal\.ArrayComparisonFailure)(?::|$)', log))
        accepted = run.returncode == 0 and counts is not None and int(counts[1]) == 105 and int(counts[2]) == assertions and assertions > 0 and 'Exception in thread ' not in log
        results.append({'variant': name, 'driver_exit': run.returncode, 'tests': int(counts[1]) if counts else None,
                        'assertion_failures': assertions, 'accepted': accepted,
                        'mutated_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        print(results[-1], flush=True)
    summary = {'source_root': str(root), 'results': results, 'accepted': all(x['accepted'] for x in results),
               'scope': 'Exact UI fragments with real files, Android framework and SQLite; explicit Compose/native player boundaries.'}
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not summary['accepted']: raise RuntimeError('Mutation did not reach the expected assertions')

if __name__ == '__main__': main()
