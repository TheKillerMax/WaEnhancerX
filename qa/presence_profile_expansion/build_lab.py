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
from presence_profile_expansion.probe.build_presence_art_probe import compiler_contract, require_quiet_d8
from presence_profile_expansion.guard import context_check, TARGET_NAMES, BASE, REF, checked_sources

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = HERE / 'lock.json'
SOURCE = '7814908a1213d86f05ef5dc068b548d322a24d94'
LAB_REF = REF
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
    require(lock['schema'] == 'WAEX_PRESENCE_PROFILE_LAB_V1' and lock['source_revision'] == SOURCE,
            'ART lock source/schema differs')
    require(lock.get('probe_origin_revision') == 'c2fd668da20f8620112d649b34224559cab30942'
            and lock.get('probe_revision_source') == 'workflow_commit' and 'probe_revision' not in lock,
            'ART probe origin/revision policy differs')
    require(len(lock['probe_sources']) == 7 and len(lock['source_files']) == 7,
            'ART source closure changed')
    require(lock['targets'] == list(TARGET_NAMES) and lock['base_revision'] == BASE, 'New Presence target/base set changed')
    require(sum(row['bytes'] for row in lock['jars']) == 429605 and len(lock['jars']) == 2,
            'Public JAR closure differs')
    require(set(lock['toolchain_source_sha256']) == {
                'qa/class_metadata_art_probe/toolchain.py',
                'qa/class_metadata_art_probe/toolchain-lock.json'}, 'Compiler source closure differs')
    verify_files(ROOT, lock['toolchain_source_sha256'])
    return lock


def validate_toolchain_receipt(value):
    module, recipe = compiler_contract()
    require(value['schema'] == recipe['schema']
            and value['lock_sha256'] == digest(module.LOCK)
            and value['helper_sha256'] == digest(Path(module.__file__))
            and value['artifacts'] == recipe['artifacts'], 'Compiler receipt recipe differs')
    require(re.fullmatch(r'info: kotlinc-jvm 2\.0\.20 \(JRE 21(?:[.+][^)]*)?\)', value['kotlin_version_output'])
            and re.fullmatch(r'[a-f0-9]{64}', value['launcher_sha256']), 'Compiler receipt version/launcher differs')
    java = value['java']
    require(java['properties']['java.specification.version'] == '21'
            and re.fullmatch(r'javac 21(?:\.[^\s]+)?', java['javac_version'])
            and set(java['files_sha256']) == {'bin/java', 'bin/javac', 'release', 'lib/modules',
                                            'lib/ct.sym', 'lib/server/libjvm.so'}
            and all(re.fullmatch(r'[a-f0-9]{64}', pin) for pin in java['files_sha256'].values()),
            'Compiler receipt JDK21 identity differs')
    return value


def validate_d8_receipt(value):
    require(set(value) == {'stdout', 'stderr'}
            and all(type(row.get('bytes')) is int for row in value.values())
            and value == {stream: {'file': 'd8.' + stream + '.log', 'bytes': 0,
                              'sha256': hashlib.sha256(b'').hexdigest()}
                      for stream in ('stdout', 'stderr')}, 'D8 diagnostics were not empty')
    return value


def probe_provenance(lock, workflow_commit):
    require(re.fullmatch(r'[a-f0-9]{40}', workflow_commit or ''), 'Exact workflow commit required')
    return {'probe_origin_revision': lock['probe_origin_revision'], 'probe_revision': workflow_commit}


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
    context_check(os.environ)
    lock = checked_lock()
    source = args.source.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reports = out / 'reports'; reports.mkdir()
    artifact = out / 'artifact'; artifact.mkdir()
    deps = out / 'deps'; deps.mkdir()
    build = out / 'offline-builder'
    result = {'schema': 'WAEX_PRESENCE_PROFILE_BUILD_V1', 'status': 'BLOCKED', 'source_revision': SOURCE,
              'workflow_commit': os.environ['GITHUB_SHA'], 'lock_sha256': digest(LOCK),
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'builder_sha256': digest(Path(__file__)),
              'toolchain_source_sha256': lock['toolchain_source_sha256'],
              'installed': False, 'art_execution': 'NOT_RUN', 'acquisitions': []}
    try:
        result.update(probe_provenance(lock, result['workflow_commit']))
        require(tool(['git', '-C', ROOT, 'rev-parse', 'HEAD'], os.environ) == result['workflow_commit'],
                'Probe checkout differs from the workflow commit')
        require(shutil.disk_usage(out).free >= 20 * 1024**3, 'Keep 20 GiB free')
        require(tool(['git', '-C', source, 'rev-parse', 'HEAD'], os.environ) == SOURCE,
                'Source checkout revision differs')
        require(not tool(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'], os.environ),
                'Source checkout is modified')
        verify_files(source, lock['source_files'])
        verify_files(ROOT, lock['probe_sources'])
        toolchain, recipe = compiler_contract()
        kotlin, env, toolchain_receipt = toolchain.prepare(out, args.java_home)
        validate_toolchain_receipt(toolchain_receipt)
        result['kotlin_toolchain'] = toolchain_receipt
        java_home = Path(toolchain_receipt['java']['java_home'])
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join((str(ROOT / 'qa'), str(source / 'qa'))))
        java_version = tool([java_home / 'bin/java', '-version'], env)
        kotlin_home = kotlin.parents[1]
        kotlin_version = toolchain_receipt['kotlin_version_output']
        jars = [kotlin_home / 'lib' / row['file'] for row in recipe['artifacts']]
        inputs = [java_home / 'bin/java', java_home / 'bin/javac',
                  java_home / 'bin/jar', java_home / 'bin/keytool',
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
        command = [sys.executable, str(HERE / 'probe/build_presence_art_probe.py'),
                   '--source-root', str(source), '--out', str(build),
                   '--sdk', str(args.sdk.resolve()), '--java-home', str(java_home),
                   '--kotlin-home', str(kotlin_home), '--deps', str(deps),
                   '--producer-commit', result['workflow_commit'], '--producer-run-id', result['run_id'],
                   '--producer-attempt', result['attempt']]
        invoke(reports, 'offline-builder', command, env, timeout=600)
        built = json.loads((build / 'build-result.json').read_text(encoding='utf-8'))
        producer={'workflow_commit':result['workflow_commit'],'run_id':result['run_id'],'attempt':result['attempt']}
        require(built['producer_identity'] == producer, 'Embedded producer provenance differs')
        result['producer_identity'] = producer
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
        require(built['compiler']['recipe_sha256'] == toolchain_receipt['lock_sha256']
                and built['compiler']['helper_sha256'] == toolchain_receipt['helper_sha256']
                and built['compiler']['kotlin_version'] == toolchain_receipt['kotlin_version_output']
                and built['compiler']['files'] == {row['file']: {'bytes': row['bytes'], 'sha256': row['sha256']}
                                                    for row in recipe['artifacts']},
                'Offline builder compiler differs from the prepared closure')
        diagnostics = require_quiet_d8(build)
        require(built['d8_diagnostics'] == diagnostics, 'Offline D8 receipt differs from raw streams')
        result['d8_diagnostics'] = validate_d8_receipt(diagnostics)
        toolchain.verify_after_build(kotlin, toolchain_receipt)
        require(result['tools']['files'] == {str(p): digest(p) for p in inputs}, 'Build tool changed during compilation')
        verify_files(source, lock['source_files'])
        verify_files(ROOT, lock['probe_sources'])
        apk = build / 'presence-art-positive.apk'
        require(apk.stat().st_size == built['apk_bytes'] and digest(apk) == built['apk_sha256']
                and 0 < apk.stat().st_size < 2 * 1024**2, 'APK identity/size differs')
        shutil.copyfile(apk, artifact / 'presence-art-positive.apk')
        require(not (build / 'qa-only.jks').exists(), 'Ephemeral key still present')
        result.update(status='PASS_BUILD_ONLY', package=PACKAGE, expected_tests=4, min_sdk=24, target_sdk=28,
                      ephemeral_key_absent=True,
                      renderer_harness_sha256=lock['renderer_harness_sha256'],
                      apk={'bytes': apk.stat().st_size, 'sha256': digest(apk)})
        save(artifact / 'artifact-manifest.json', result)
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        (build / 'qa-only.jks').unlink(missing_ok=True)
        result['ephemeral_key_absent'] = not (build / 'qa-only.jks').exists()
        for name in ('kotlin-toolchain.json', 'kotlin-version.stdout.log', 'kotlin-version.stderr.log'):
            path = out / name
            if path.is_file():
                shutil.copyfile(path, reports / name)
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
