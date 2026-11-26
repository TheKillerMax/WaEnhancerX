#!/usr/bin/env python3
"""Explicit admission and provenance for seventeen previously untested ART cells."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPOSITORY = 'TheKillerMax/WaEnhancerX'
REF = 'refs/heads/lab/classmetadata-profile-expansion-20261126'
BASE = '1e666077571c39896b7fcadbf7c549b440d51a86'
MATRIX_SHA = '29b25a9d8f7068a8586f5c92d485b95e3b6cb761c8bb86868924c34f79677fc0'
TARGET_NAMES = ('api25', 'api26', 'api27', 'api28', 'api29', 'api31', 'api32',
                'api35', 'api36', 'api37', 'api36.1', 'api35-16k', 'api36-16k',
                'api36.1-16k', 'api37-16k', 'api37.1-16k', 'api37.2-16k')
QUALIFIED_TARGETS = ('api24', 'api30', 'api33', 'api34')
SOURCE_NAMES = tuple('qa/class_metadata_profile_expansion/' + name for name in
                     ('ExpansionMain.java', 'build.py', 'run.py', 'validate_expansion.py',
                      'expansion_contract.py', 'expansion_pilot.py', 'bootstrap.py')) + (
                          '.github/workflows/android-class-metadata-profile-expansion.yml',)
INHERITED_NAMES = (
    'qa/android_emulator_lab_preflight.py', 'qa/android_emulator_lab_bootstrap.py',
    'qa/android_emulator_lab_pilot.py', 'qa/android_emulator_lab_matrix.py',
    'qa/android_emulator_lab_adb.py', 'qa/summarize_android_emulator_lab_matrix.py',
    'qa/build_android_sqlite_probe.py', 'qa/validate_android_sqlite_probe.py',
    'qa/test_android_sqlite_probe.py', 'qa/ANDROID_SQLITE_PROBE.md',
    'qa/android_sqlite_probe/AndroidManifest.xml',
    'qa/android_sqlite_probe/SqliteProbeInstrumentation.java',
)
TARGETS = {}
for name in TARGET_NAMES:
    label = name.removeprefix('api').removesuffix('-16k')
    major = int(label.split('.')[0])
    version = label + '.0' if label == '37' else label
    tag = 'google_apis_ps16k' if name.endswith('-16k') else ('default' if major in (27, 31, 32) else 'google_apis')
    TARGETS[name] = (major, 'system-images;android-' + version + ';' + tag + ';x86_64',
                     16384 if name.endswith('-16k') else 4096)
VARIANTS = ('baseline', 'candidate')
CANONICAL = {
    'repository': REPOSITORY, 'run_id': '45699162692', 'attempt': '1',
    'workflow_commit': 'c26f330a3cbd5d26807f1b9358daa46a62d26f3a',
    'artifact_id': 15060793987, 'artifact_name': 'classmeta-build-45699162692-1',
    'archive_bytes': 1741478,
    'archive_sha256': '3a1db8e375b26893d0625952d3ff2a52e739ebffb7479530ef899ba5f27189b5',
    'manifest_sha256': '76c2a3397d81bab85e341fc4c7adba5618e5b27afd70b8b391bd886b64702191',
    'manifest_bytes': 48905,
    'probe_source_sha256': 'a4d35eb6ba25990b1a8bfdcfe967c5f869f3c89e7edf6c78aa6d22d20f0fa593',
    'source_lock_sha256': '6ed524c843e9e67533e776f121e55aac91969dc27ae2cdf6fcd08dd77c2be771',
    'builder_sha256': 'd9446d12e6479503bcdd8d6d59a2839aeec40072ac1d0d7479e4958d6d675e60',
    'variants': {
        'baseline': {'jar_bytes': 2750884,
                     'jar_sha256': '3e6378e13dee4ac9af960dcda75ed92f5d314fa6736aee4c996888d9151a9fa8'},
        'candidate': {'jar_bytes': 2750584,
                      'jar_sha256': '44526934c737ed2e53376560e4474013896f0f2dee19d111e13fbbd766d1c47e'},
    },
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def minor(target):
    require(target in TARGETS, 'Target is outside the seventeen pending cells')
    label = target.removeprefix('api').removesuffix('-16k')
    return int(label.split('.')[1]) if '.' in label else 0


def load_lock(verify_sources=True):
    path = HERE / 'lock.json'
    require(path.is_file() and not path.is_symlink(), 'Expansion lock missing or redirected')
    lock = json.loads(path.read_bytes())
    require(lock.get('schema') == 'WAEX_ART_PROFILE_EXPANSION_LOCK_V1' and
            lock.get('base_commit') == BASE and lock.get('repository') == REPOSITORY and
            lock.get('ref') == REF, 'Expansion admission identity differs')
    require(lock.get('targets') == list(TARGET_NAMES) and
            lock.get('excluded_qualified_targets') == list(QUALIFIED_TARGETS),
            'Expansion must contain exactly seventeen pending cells')
    require(lock.get('canonical_producer') == CANONICAL and
            lock.get('historical_matrix_lock_sha256') == MATRIX_SHA,
            'Canonical provenance or matrix pin differs')
    require(set(lock.get('source_sha256', {})) == set(SOURCE_NAMES) and
            set(lock.get('inherited_source_sha256', {})) == set(INHERITED_NAMES),
            'Source pin coverage differs')
    if verify_sources:
        for group in ('source_sha256', 'inherited_source_sha256'):
            pins = lock.get(group)
            require(isinstance(pins, dict) and pins, 'Missing source pins: ' + group)
            for rel, expected in pins.items():
                p = ROOT / rel
                require(re.fullmatch(r'(?:qa|\.github)/[A-Za-z0-9_./-]+', rel) and
                        '..' not in Path(rel).parts and re.fullmatch(r'[0-9a-f]{64}', expected) and
                        p.is_file() and not p.is_symlink() and digest(p) == expected,
                        'Pinned source differs: ' + rel)
        matrix = ROOT / 'qa/android_emulator_lab_matrix_lock.json'
        require(matrix.is_file() and not matrix.is_symlink() and digest(matrix) == MATRIX_SHA,
                'The qualified twenty-one-profile matrix lock changed')
    return lock


def context_check(env, *, verify_sources=True):
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPOSITORY and
            env.get('GITHUB_REF') == REF and env.get('GITHUB_EVENT_NAME') == 'push',
            'Only the named public fork push on the new expansion branch is admitted')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1' and
            re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')) and
            re.fullmatch(r'[0-9a-f]{40}', env.get('GITHUB_SHA', '')),
            'Only the first attempt of a concrete producer run is admitted')
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_bytes())
    repo = event.get('repository', {})
    require(repo.get('full_name') == REPOSITORY and repo.get('private') is False and
            event.get('ref') == REF and event.get('after') == env['GITHUB_SHA'] and
            event.get('deleted') is False and event.get('forced') is False,
            'Push event does not describe the admitted public branch/head')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'Expansion requires the isolated Linux x86_64 runner')
    return load_lock(verify_sources=verify_sources)


def verify_canonical(bundle):
    expected = {'artifact-manifest.json', 'baseline-art-probe.jar', 'candidate-art-probe.jar'}
    require(bundle.is_dir() and not bundle.is_symlink() and
            {p.name for p in bundle.iterdir()} == expected, 'Historical artifact members differ')
    manifest = bundle / 'artifact-manifest.json'
    require(manifest.is_file() and not manifest.is_symlink() and
            manifest.stat().st_size == CANONICAL['manifest_bytes'] and
            digest(manifest) == CANONICAL['manifest_sha256'], 'Historical producer manifest differs')
    value = json.loads(manifest.read_bytes())
    required = {'schema': 'WAEX_CLASS_METADATA_ART_BUILD_V2', 'status': 'PASS_BUILD_ONLY',
                'workflow_commit': CANONICAL['workflow_commit'], 'run_id': CANONICAL['run_id'],
                'attempt': CANONICAL['attempt'], 'lock_sha256': CANONICAL['source_lock_sha256'],
                'probe_sha256': CANONICAL['probe_source_sha256'],
                'builder_sha256': CANONICAL['builder_sha256'], 'art_executed': False}
    for key, expected in required.items():
        require(type(value.get(key)) is type(expected) and value[key] == expected,
                'Historical manifest field differs: ' + key)
    require(set(value.get('variants', {})) == set(VARIANTS), 'Historical variants differ')
    for variant in VARIANTS:
        p = bundle / (variant + '-art-probe.jar')
        pin = CANONICAL['variants'][variant]
        require(p.is_file() and not p.is_symlink() and p.stat().st_size == pin['jar_bytes'] and
                digest(p) == pin['jar_sha256'], 'Historical JAR differs: ' + variant)
        receipt = value['variants'][variant]
        require(all(receipt.get(k) == v for k, v in pin.items()) and
                receipt.get('host_checks') == 702 and receipt.get('host_scenarios') == 101,
                'Historical qualification provenance differs: ' + variant)
    return value
