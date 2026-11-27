#!/usr/bin/env python3
"""Exercise the real overlay settings launcher with Robolectric Android Intents.

Reuse the public dependencies and API 24/28/34 SDK cache prepared by the other
framework runners. No fake Android Intent or Settings classes are generated.
This suite does not build Compose or certify an OEM settings application.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('app/src/main/java/com/waenhancer/app/OverlayPermissionLauncher.java')
TEST = Path('qa/fixtures/overlay_settings/OverlayPermissionLauncherTest.java')
EXPECTED_TESTS = 30  # Ten behavior cases, each on API 24, 28 and 34.


def run(command, log):
    result = subprocess.run(command, capture_output=True, timeout=180)
    log.write_bytes(result.stdout + result.stderr)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deps', type=Path, required=True)
    parser.add_argument('--sdk-jars', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('--out must be empty to preserve earlier evidence')
    out.mkdir(parents=True, exist_ok=True)
    classes = out / 'classes'
    classes.mkdir()
    root = args.source_root.resolve()
    source = root / SOURCE
    fixture = ROOT / TEST
    dependencies = sorted(args.deps.resolve().glob('*.jar'))
    if not dependencies or not any(p.name == 'android-all-14-robolectric-10818077.jar' for p in dependencies):
        raise RuntimeError('The dependency cache must include the real Android 34 API JAR')
    source_hashes = {str(SOURCE): hashlib.sha256(source.read_bytes()).hexdigest(),
                     str(TEST): hashlib.sha256(fixture.read_bytes()).hexdigest(),
                     'qa/test_overlay_settings.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    resources = {'overlay_settings_help', 'overlay_open_app_info', 'overlay_settings_unavailable'}
    for locale in ('values', 'values-es', 'values-b+es+419', 'values-sl'):
        path = root / 'app/src/main/res' / locale / 'overlay_permission.xml'
        strings = ET.parse(path).getroot().findall('string')
        if {s.get('name') for s in strings} != resources or any(not s.text for s in strings):
            raise RuntimeError('Missing or empty overlay settings resource in ' + str(path))
        source_hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    cp = os.pathsep.join(map(str, dependencies))
    java = shutil.which('java')
    javac = shutil.which('javac')
    if not java or not javac:
        raise RuntimeError('A complete JDK 17 or later is required')
    if run([javac, '--release', '17', '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes),
            str(source), str(fixture)], out / 'javac.log'):
        raise RuntimeError('Production or test compilation failed; see javac.log')
    opens = ['java.base/java.lang', 'java.base/java.util', 'java.base/java.util.concurrent',
             'java.base/java.io', 'java.base/java.net', 'java.base/java.security',
             'java.base/java.text', 'java.base/jdk.internal.access', 'java.desktop/java.awt.font']
    result = run([java, '-Xmx1g', *['--add-opens=' + p + '=ALL-UNNAMED' for p in opens],
                  '-Drobolectric.offline=true', '-Drobolectric.dependency.dir=' + str(args.sdk_jars.resolve()),
                  '-cp', str(classes) + os.pathsep + cp, 'org.junit.runner.JUnitCore',
                  'com.waenhancer.app.OverlayPermissionLauncherTest'], out / 'junit.log')
    output = (out / 'junit.log').read_text(encoding='utf-8')
    match = re.search(r'OK \((\d+) tests?\)', output)
    failure = re.search(r'Tests run: (\d+),  Failures: (\d+)', output)
    accepted = result == 0 and match is not None and int(match.group(1)) == EXPECTED_TESTS
    report = {'junit_exit_code': result, 'expected_tests': EXPECTED_TESTS,
              'tests': int(match.group(1)) if match else int(failure.group(1)) if failure else 0,
              'failures': int(failure.group(2)) if failure else 0, 'accepted_result': accepted,
              'source_sha256': source_hashes,
              'dependency_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},
              'sdk_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(args.sdk_jars.resolve().glob('*.jar'))},
              'scope': __doc__}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not accepted:
        raise RuntimeError('Unexpected overlay settings result; see junit.log')
    print('PASS: 10 overlay settings behaviors across API 24/28/34 (30 JUnit executions)')


if __name__ == '__main__':
    main()
