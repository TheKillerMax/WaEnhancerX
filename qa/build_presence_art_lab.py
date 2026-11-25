#!/usr/bin/env python3
"""Build the pinned ART probe once on an isolated public Linux runner."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from android_emulator_lab_pilot import invoke, require

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'presence_art_lab_lock.json'
SOURCE = 'c52f064bad7ba32445f8515bc2f0421618438975'
LAB_REF = 'refs/heads/lab/android-emulator-matrix-nightly8-20261124'
PACKAGE = 'org.waex.qa.presence.host'


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def verify_files(root, pins):
    for relative, expected in pins.items():
        path = root / relative
        require(not path.is_symlink() and path.is_file() and digest(path) == expected,
                'Pinned source differs: ' + relative)


def checked_lock():
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    require(lock['schema'] == 'WAEX_ART_LAB_V1' and lock['source_revision'] == SOURCE,
            'ART lock source/schema differs')
    require(len(lock['probe_sources']) == 8 and len(lock['source_files']) == 7,
            'ART source closure changed')
    require(lock['targets'] == ['api24', 'api25', 'api26'], 'ART target set changed')
    require(sum(row['bytes'] for row in lock['jars']) == 429605 and len(lock['jars']) == 2,
            'Public JAR closure differs')
    return lock


def verify_jar(path, pin):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == pin['bytes'],
            'JAR size/type differs')
    for algorithm in ('sha1', 'sha256', 'sha512'):
        require(digest(path, algorithm) == pin[algorithm], 'JAR digest differs: ' + algorithm)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Pinned Maven URL redirected; no alternative origin requested')


def acquire(pin, target, receipt, opener=None):
    parsed = urllib.parse.urlsplit(pin['url'])
    require(parsed.scheme == 'https' and parsed.netloc == 'repo.maven.apache.org'
            and not parsed.query and not parsed.fragment, 'Unapproved JAR URL')
    require(not target.exists(), 'Fresh acquisition target required')
    receipt.update(url=pin['url'], attempts=1, status='REQUESTED')
    opener = opener or urllib.request.build_opener(NoRedirect()).open
    partial = target.with_suffix(target.suffix + '.partial')
    try:
        with opener(urllib.request.Request(pin['url'], headers={'User-Agent': 'WAEX-ART-lab/1'}),
                    timeout=60) as response, partial.open('xb') as stream:
            require(response.status == 200, 'Unexpected JAR HTTP status')
            total = 0
            while block := response.read(65536):
                total += len(block)
                require(total <= pin['bytes'], 'JAR exceeded pinned size')
                stream.write(block)
        verify_jar(partial, pin)
        partial.replace(target)
        receipt.update(status='VERIFIED', bytes=total, sha256=digest(target))
    except urllib.error.HTTPError as error:
        receipt.update(status='HTTP_FAILURE', code=error.code,
                       retry_after=error.headers.get('Retry-After'))
        raise RuntimeError('HTTP ' + str(error.code) + '; no retry attempted') from error
    finally:
        partial.unlink(missing_ok=True)


def tool(command, env):
    result = subprocess.run(list(map(str, command)), env=env, capture_output=True, timeout=20)
    require(result.returncode == 0 and len(result.stdout) + len(result.stderr) < 65536,
            'Build tool identity failed')
    return (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_REPOSITORY') == 'TheKillerMax/WaEnhancerX'
            and os.environ.get('GITHUB_REF') == LAB_REF, 'Isolated fork Linux job required')
    lock = checked_lock()
    source = args.source.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reports = out / 'reports'; reports.mkdir()
    artifact = out / 'artifact'; artifact.mkdir()
    deps = out / 'deps'; deps.mkdir()
    build = out / 'offline-builder'
    result = {'schema': 'WAEX_ART_BUILD_V1', 'status': 'BLOCKED', 'source_revision': SOURCE,
              'workflow_commit': os.environ['GITHUB_SHA'], 'lock_sha256': digest(LOCK),
              'installed': False, 'art_execution': 'NOT_RUN', 'acquisitions': []}
    try:
        require(shutil.disk_usage(out).free >= 20 * 1024**3, 'Keep 20 GiB free')
        require(tool(['git', '-C', source, 'rev-parse', 'HEAD'], os.environ) == SOURCE,
                'Source checkout revision differs')
        require(not tool(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'], os.environ),
                'Source checkout is modified')
        verify_files(source, lock['source_files'])
        verify_files(HERE.parent, lock['probe_sources'])
        java_home = args.java_home.resolve()
        env = dict(os.environ, JAVA_HOME=str(java_home), JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2',
                   PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(source / 'qa'))
        java_version = tool([java_home / 'bin/java', '-version'], env)
        require(re.search(r'\bversion "21[.]', java_version), 'Existing JDK21 required')
        kotlin_exe = shutil.which('kotlinc')
        require(kotlin_exe is not None, 'Preinstalled Kotlin CLI required')
        kotlin_home = Path(kotlin_exe).resolve().parent.parent
        kotlin_version = tool([kotlin_exe, '-version'], env)
        require('kotlinc-jvm 2.4.21 ' in kotlin_version, 'Expected observed Kotlin 2.4.21')
        jars = sorted((kotlin_home / 'lib').glob('*.jar'))
        require(jars and (kotlin_home / 'lib/kotlin-stdlib.jar').is_file(), 'Kotlin closure missing')
        inputs = [java_home / 'bin/java', java_home / 'bin/javac',
                  args.sdk / 'platforms/android-36/android.jar',
                  args.sdk / 'build-tools/36.0.0/aapt2',
                  args.sdk / 'build-tools/36.0.0/zipalign',
                  args.sdk / 'build-tools/36.0.0/lib/d8.jar',
                  args.sdk / 'build-tools/36.0.0/lib/apksigner.jar', *jars]
        require(all(p.is_file() for p in inputs), 'Existing SDK36/build-tools36 inputs missing')
        result['tools'] = {'java_version': java_version, 'kotlin_version': kotlin_version,
                           'kotlin_home': str(kotlin_home), 'files': {str(p): digest(p) for p in inputs}}
        for pin in lock['jars']:
            receipt = {}; result['acquisitions'].append(receipt)
            acquire(pin, deps / pin['name'], receipt)
        command = [sys.executable, str(HERE / 'presence_art_probe/build_presence_art_probe.py'),
                   '--source-root', str(source), '--out', str(build),
                   '--sdk', str(args.sdk.resolve()), '--java-home', str(java_home),
                   '--kotlin-home', str(kotlin_home), '--deps', str(deps)]
        invoke(reports, 'offline-builder', command, env, timeout=600)
        built = json.loads((build / 'build-result.json').read_text(encoding='utf-8'))
        require(built['build_status'] == 'PASS' and built['installed'] is False
                and built['art_execution'] == 'NOT_RUN' and not built['qa_signing_key_retained']
                and not built['source_changes'] and built['package'] == PACKAGE
                and built['expected_tests'] == 4 and built['min_sdk'] == 24 and built['target_sdk'] == 28,
                'Offline build receipt failed')
        require(built['positive_extracted_harness_sha256'] == lock['renderer_harness_sha256']
                and built['compiled_harness_sha256'] == lock['renderer_harness_sha256'],
                'Original renderer harness differs')
        require({k: v['raw_sha256'] for k, v in built['inputs'].items()} == lock['source_files'],
                'Builder source closure differs from lock')
        require(len(built['oracles']) == 2 and all(row['assertion_text_preserved'] for row in built['oracles']),
                'Original pixel assertions were not preserved')
        verify_files(source, lock['source_files'])
        verify_files(HERE.parent, lock['probe_sources'])
        apk = build / 'presence-art-positive.apk'
        require(apk.stat().st_size == built['apk_bytes'] and digest(apk) == built['apk_sha256']
                and 0 < apk.stat().st_size < 2 * 1024**2, 'APK identity/size differs')
        shutil.copyfile(apk, artifact / 'presence-art-positive.apk')
        require(not (build / 'qa-only.jks').exists(), 'Ephemeral key still present')
        result.update(status='PASS_BUILD_ONLY', package=PACKAGE, expected_tests=4, min_sdk=24, target_sdk=28,
                      ephemeral_key_absent=True,
                      renderer_harness_sha256=lock['renderer_harness_sha256'],
                      probe_revision=lock['probe_revision'], apk={'bytes': apk.stat().st_size, 'sha256': digest(apk)})
        save(artifact / 'artifact-manifest.json', result)
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        (build / 'qa-only.jks').unlink(missing_ok=True)
        result['ephemeral_key_absent'] = not (build / 'qa-only.jks').exists()
        if build.exists():
            for path in sorted(build.glob('*')):
                if path.is_file() and path.suffix in ('.json', '.log'):
                    require(path.stat().st_size <= 8 * 1024**2, 'Oversized offline build report')
                    dest = reports / 'offline-builder'; dest.mkdir(exist_ok=True)
                    shutil.copyfile(path, dest / path.name)
        save(reports / 'build-result.json', result)
        save(reports / 'manifest.json', {p.relative_to(reports).as_posix():
             {'bytes': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(reports.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS_BUILD_ONLY' and result['ephemeral_key_absent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
