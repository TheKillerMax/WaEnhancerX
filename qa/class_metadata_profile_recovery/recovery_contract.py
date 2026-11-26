#!/usr/bin/env python3
"""Exact recovery admission: fifteen pending canonical processes and two separate cache fixtures."""
import hashlib
import json
from pathlib import Path
import platform
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPOSITORY = 'TheKillerMax/WaEnhancerX'
REF = 'refs/heads/lab/classmetadata-profile-recovery-20261126'
BASE = '83012b298e555d8b3c87cbbec67e250582bfdb72'
PRIOR_RUN = '45742530551'
PRESENCE_PRIOR_RUN = '45743982684'
PRESENCE_PRIOR_HEAD = 'd2b432a97a1d1250e365bc0a0a6822fbcd192dbb'
MATRIX_SHA = '29b25a9d8f7068a8586f5c92d485b95e3b6cb761c8bb86868924c34f79677fc0'
RUNTIME_VARIANTS = {
    'api26': ('baseline', 'candidate'), 'api29': ('baseline', 'candidate'),
    'api35': ('baseline', 'candidate'), 'api36': ('baseline', 'candidate'),
    'api35-16k': ('candidate',), 'api36-16k': ('baseline', 'candidate'),
    'api36.1-16k': ('baseline', 'candidate'), 'api37-16k': ('baseline', 'candidate'),
}
TARGET_NAMES = tuple(RUNTIME_VARIANTS)
CACHE_TARGET_NAMES = ('api27', 'api28')
QUALIFIED_TARGETS = ('api24', 'api25', 'api27', 'api28', 'api30', 'api31', 'api32',
                     'api33', 'api34', 'api36.1', 'api37', 'api37.1-16k', 'api37.2-16k')
SOURCE_NAMES = tuple('qa/class_metadata_profile_recovery/' + name for name in
    ('ExpansionMain.java', 'build.py', 'run.py', 'validate_recovery.py', 'recovery_contract.py',
     'recovery_pilot.py', 'bootstrap.py', 'reviewed_adb.py', 'apt_observation.py', 'README.md',
     'prior-evidence/NONCE_LEDGER.json', 'prior-evidence/RECOVERY_SELECTION.json',
     'prior-evidence/PRESENCE15_NONCE_LEDGER.json',
     'prior-evidence/api35-16k-baseline-validated.json', 'prior-evidence/api35-16k-phase.json')) + (
        '.github/workflows/android-class-metadata-profile-recovery.yml',) + tuple(
            'qa/art_cache_recovery/' + name for name in
            ('CacheLifecycleMain.java', 'build.py', 'run.py', 'validate.py', 'owned_tree.py', 'README.md'))
INHERITED_NAMES = ('qa/android_emulator_lab_preflight.py', 'qa/android_emulator_lab_bootstrap.py', 'qa/android_emulator_lab_pilot.py', 'qa/android_emulator_lab_matrix.py', 'qa/summarize_android_emulator_lab_matrix.py', 'qa/build_android_sqlite_probe.py', 'qa/validate_android_sqlite_probe.py', 'qa/test_android_sqlite_probe.py', 'qa/ANDROID_SQLITE_PROBE.md', 'qa/android_sqlite_probe/AndroidManifest.xml', 'qa/android_sqlite_probe/SqliteProbeInstrumentation.java', 'qa/android_emulator_lab_adb.py', '.github/workflows/android-class-metadata-profile-expansion.yml', 'qa/class_metadata_profile_expansion/ExpansionMain.java', 'qa/class_metadata_profile_expansion/README.md', 'qa/class_metadata_profile_expansion/bootstrap.py', 'qa/class_metadata_profile_expansion/build.py', 'qa/class_metadata_profile_expansion/expansion_contract.py', 'qa/class_metadata_profile_expansion/expansion_pilot.py', 'qa/class_metadata_profile_expansion/lock.json', 'qa/class_metadata_profile_expansion/run.py', 'qa/class_metadata_profile_expansion/validate_expansion.py')
PRIOR_EVIDENCE = {'NONCE_LEDGER.json': {'bytes': 15787,
                       'sha256': '671c9763683ccfe3aa76860433201aae6b1f0b0503644ab3c5001abf92a51298'},
 'RECOVERY_SELECTION.json': {'bytes': 11319,
                             'sha256': '7ff86b3791a8cd36d08d4f9214d3911a942b8c21d81cd5f1bf0b4f7b8c6f710f'},
 'api35-16k-baseline-validated.json': {'bytes': 2765,
                                       'sha256': 'e637d5021d95b9ce1343cb51333f7666e309f624e1c61d67ea1d03fa2a371c6e'},
 'api35-16k-phase.json': {'bytes': 3658,
                          'sha256': 'e4407e1651cf609a0239172e54676c100389f9a8e1cfcb7e9f64c765a5f8ff87'},
 'PRESENCE15_NONCE_LEDGER.json': {'bytes': 79023,
                                  'sha256': '23c4e9266688bbdf6f9e7137bda8971aa3d42eb20f841f1fc15b5cd173f15c59'}}
ALL_TARGETS = {}
for name in (*TARGET_NAMES, *CACHE_TARGET_NAMES):
    label = name.removeprefix('api').removesuffix('-16k')
    major = int(label.split('.')[0])
    version = label + '.0' if label == '37' else label
    tag = 'google_apis_ps16k' if name.endswith('-16k') else ('default' if major in (27, 31, 32) else 'google_apis')
    ALL_TARGETS[name] = (major, 'system-images;android-' + version + ';' + tag + ';x86_64',
                         16384 if name.endswith('-16k') else 4096)
TARGETS = RUNTIME_TARGETS = {name: ALL_TARGETS[name] for name in TARGET_NAMES}
CACHE_TARGETS = {name: ALL_TARGETS[name] for name in CACHE_TARGET_NAMES}
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
    require(target in ALL_TARGETS, 'Target is outside the separately reviewed recovery scopes')
    label = target.removeprefix('api').removesuffix('-16k')
    return int(label.split('.')[1]) if '.' in label else 0


def prior_evidence():
    result = {}
    for name, pin in PRIOR_EVIDENCE.items():
        p = HERE / 'prior-evidence' / name
        require(p.is_file() and not p.is_symlink() and p.stat().st_size == pin['bytes']
                and digest(p) == pin['sha256'], 'Previous-run evidence differs: ' + name)
        result[name] = json.loads(p.read_bytes())
    ledger = result['NONCE_LEDGER.json']
    require(ledger.get('schema') == 'WAEX_ART17_CONSUMED_CLAIMS_RECONCILIATION_V1'
            and ledger.get('run_id') == PRIOR_RUN and ledger.get('head_sha') == BASE
            and ledger.get('attempt') == '1' and ledger.get('all_claims_non_reusable') is True,
            'Previous nonce ledger identity differs')
    claims = ledger.get('claims', [])
    require(len(claims) == 30 and ledger.get('claim_count') == 30
            and ledger.get('unique_claim_count') == 30
            and all(row.get('consumed_or_reserved') is True and row.get('reusable') is False
                    and re.fullmatch(r'[0-9a-f]{32}', row.get('nonce', '')) for row in claims)
            and len({row['nonce'] for row in claims}) == 30, 'Previous claims are incomplete')
    selected = result['RECOVERY_SELECTION.json']
    require(selected.get('schema') == 'WAEX_ART17_VARIANT_RECOVERY_SELECTION_V1'
            and selected.get('parent_commit') == BASE and selected.get('original_run_id') == PRIOR_RUN
            and selected.get('original_run_attempt') == '1'
            and selected.get('selection') == {k: list(v) for k, v in RUNTIME_VARIANTS.items()}
            and selected.get('cleanup_only_new_fixture_profiles') == list(CACHE_TARGET_NAMES)
            and selected.get('baseline_api35_16k_must_not_repeat') is True
            and selected.get('prospective_canonical_process_count') == 15,
            'Previous evidence does not authorize the exact remaining process selection')
    expected_passes = {(target, variant) for target in
                       ('api25', 'api27', 'api28', 'api31', 'api32', 'api36.1', 'api37',
                        'api37.1-16k', 'api37.2-16k') for variant in VARIANTS} | {('api35-16k', 'baseline')}
    passes = selected.get('preserved_functional_passes', [])
    require(len(passes) == 19 and {(p.get('target'), p.get('variant')) for p in passes} == expected_passes
            and all(not (p['target'] in RUNTIME_VARIANTS and p['variant'] in RUNTIME_VARIANTS[p['target']])
                    for p in passes), 'A previously successful workload entered recovery')
    baseline = result['api35-16k-baseline-validated.json']
    identity = baseline.get('identity', {})
    phase = result['api35-16k-phase.json']
    known = phase.get('variants', {}).get('baseline', {})
    pending = phase.get('variants', {}).get('candidate', {})
    require(baseline.get('status') == 'PASS' and baseline.get('workload_checks') == 13
            and baseline.get('identity_checks') == 13 and identity.get('target') == 'api35-16k'
            and identity.get('variant') == 'baseline' and identity.get('canonical_sha256') == CANONICAL['variants']['baseline']['jar_sha256']
            and identity.get('host_expected', {}).get('run_id') == PRIOR_RUN
            and identity.get('host_expected', {}).get('workflow_commit') == BASE
            and known.get('status') == 'PASS' and known.get('nonce') == identity.get('nonce')
            and known.get('validated_sha256') == PRIOR_EVIDENCE['api35-16k-baseline-validated.json']['sha256']
            and pending.get('status') == 'CLAIMED_BEFORE_EXECUTION' and pending.get('attempts') == 0,
            'The omitted API35-16k baseline is not bound to its original qualified receipt')
    return result


def consumed_nonces(lock):
    evidence = prior_evidence()
    art = evidence['NONCE_LEDGER.json']
    prior = set(art['prior_physical_consumed_nonces']) | {r['nonce'] for r in art['claims']}
    presence = evidence['PRESENCE15_NONCE_LEDGER.json']
    # Emission ownership is independent of the Presence runtime audit status.
    # Keep all recognized claims, including those whose audit is still unresolved.
    require(presence.get('schema') == 'WAEX_PRESENCE15_CONSUMED_CLAIMS_V1'
            and presence.get('run_id') == PRESENCE_PRIOR_RUN
            and presence.get('head_sha') == PRESENCE_PRIOR_HEAD
            and presence.get('collection_complete') is True
            and presence.get('status') == 'COMPLETE_RECOGNIZED_EMISSIONS_NON_REUSABLE'
            and presence.get('claim_collection_issues') == [] and presence.get('collisions') == []
            and presence.get('prior_known_claims') == 38
            and presence.get('new_claim_count') == 15 and presence.get('new_unique_nonce_count') == 15
            and presence.get('combined_known_unique_count') == 53,
            'Presence claim collection is incomplete or its producer differs')
    pin = presence.get('prior_claim_ledger', {})
    require(pin.get('bytes') == PRIOR_EVIDENCE['NONCE_LEDGER.json']['bytes']
            and pin.get('sha256') == PRIOR_EVIDENCE['NONCE_LEDGER.json']['sha256'],
            'Presence claims are not linked to the preserved ART ledger')
    claims = presence.get('claims')
    require(type(claims) is list and len(claims) == 15
            and all(type(row) is dict and row.get('reusable') is False
                    and row.get('artifact_bytes_verified') is True and row.get('run_id') == PRESENCE_PRIOR_RUN
                    and type(row.get('nonce')) is str and re.fullmatch(r'[0-9a-f]{32}', row['nonce'])
                    and type(row.get('emissions')) is list and len(row['emissions']) > 0 for row in claims),
            'Presence claims lack complete non-reusable byte-verified emissions')
    additional = {r['nonce'] for r in claims}
    require(len(prior) == 38 and len(additional) == 15 and not (prior & additional),
            'The independent claim ledgers overlap or omit known claims')
    expected = prior | additional
    values = lock.get('consumed_nonces')
    require(type(values) is list and len(values) == 53 and len(set(values)) == 53
            and set(values) == expected and all(type(n) is str and re.fullmatch(r'[0-9a-f]{32}', n) for n in values),
            'All eight physical, thirty ART and fifteen Presence claims must remain excluded')
    return frozenset(values)


def load_lock(verify_sources=True):
    path = HERE / 'lock.json'
    require(path.is_file() and not path.is_symlink(), 'Recovery lock missing or redirected')
    lock = json.loads(path.read_bytes())
    require(lock.get('schema') == 'WAEX_ART_PROFILE_RECOVERY_LOCK_V1'
            and lock.get('base_commit') == BASE and lock.get('repository') == REPOSITORY
            and lock.get('ref') == REF, 'Recovery admission identity differs')
    require(lock.get('targets') == list(TARGET_NAMES)
            and lock.get('runtime_variants') == {k: list(v) for k, v in RUNTIME_VARIANTS.items()}
            and lock.get('cache_targets') == list(CACHE_TARGET_NAMES)
            and lock.get('excluded_canonical_workload_targets') == list(QUALIFIED_TARGETS),
            'Recovery must contain only the pending variants and the separate new cache fixtures')
    require(lock.get('canonical_producer') == CANONICAL
            and lock.get('historical_matrix_lock_sha256') == MATRIX_SHA
            and lock.get('prior_run_evidence') == PRIOR_EVIDENCE, 'Prior producer, evidence or matrix pins differ')
    require(set(lock.get('source_sha256', {})) == set(SOURCE_NAMES)
            and set(lock.get('inherited_source_sha256', {})) == set(INHERITED_NAMES),
            'Recovery source pin coverage differs')
    if verify_sources:
        for group in ('source_sha256', 'inherited_source_sha256'):
            for rel, expected in lock[group].items():
                p = ROOT / rel
                require(re.fullmatch(r'(?:qa|\.github)/[A-Za-z0-9_./-]+', rel)
                        and '..' not in Path(rel).parts and re.fullmatch(r'[0-9a-f]{64}', expected)
                        and p.is_file() and not p.is_symlink() and digest(p) == expected,
                        'Pinned recovery or preserved source differs: ' + rel)
        matrix = ROOT / 'qa/android_emulator_lab_matrix_lock.json'
        require(matrix.is_file() and not matrix.is_symlink() and digest(matrix) == MATRIX_SHA,
                'The qualified twenty-one-profile matrix lock changed')
    consumed_nonces(lock)
    return lock


def context_check(env, *, verify_sources=True):
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REF') == REF and env.get('GITHUB_EVENT_NAME') == 'push',
            'Only the named public fork push on the new recovery branch is admitted')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1'
            and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', ''))
            and re.fullmatch(r'[0-9a-f]{40}', env.get('GITHUB_SHA', '')),
            'Only the first attempt of a concrete recovery producer is admitted')
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_bytes())
    repo = event.get('repository', {})
    require(repo.get('full_name') == REPOSITORY and repo.get('private') is False
            and event.get('ref') == REF and event.get('after') == env['GITHUB_SHA']
            and event.get('deleted') is False and event.get('forced') is False,
            'Push event does not describe the admitted public recovery branch/head')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'Recovery requires the isolated Linux x86_64 runner')
    return load_lock(verify_sources=verify_sources)


def checked_matrix(path, target):
    from android_emulator_lab_matrix import checked_lock
    require(path.resolve() == (ROOT / 'qa/android_emulator_lab_matrix_lock.json').resolve()
            and digest(path) == MATRIX_SHA and target in ALL_TARGETS, 'Matrix path or target outside reviewed recovery')
    value, entry = checked_lock(path, target)
    api, image_path, pages = ALL_TARGETS[target]
    require((entry['image']['path'], entry['image']['api'], entry['image']['minor'],
             entry['application_page_size_bytes']) == (image_path, api, minor(target), pages),
            'Selected recovery image differs from the historical matrix')
    return value, entry


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
