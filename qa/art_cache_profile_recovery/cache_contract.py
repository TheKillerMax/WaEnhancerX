#!/usr/bin/env python3
"""Dedicated admission for two unexecuted cache fixtures; no canonical workload entrypoint."""
import json
from pathlib import Path
import platform
import re

from class_metadata_profile_recovery import recovery_contract as prior
from class_metadata_profile_recovery.recovery_contract import digest, require, save

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPOSITORY = 'TheKillerMax/WaEnhancerX'
REF = 'refs/heads/lab/art-cache-profile-recovery-20261126'
BASE = 'a8bea4fbf9ddefab6984e464eb24270a121cc659'
PRIOR_RUN = '45749434077'
PARENT_LOCK_SHA = '65bb21afe6d39f610cfa3e06136cd374686058817deb9472feed443b2f80c8da'
REFERENCE_SHA = '76c2a3397d81bab85e341fc4c7adba5618e5b27afd70b8b391bd886b64702191'
CACHE_TARGETS = {name: prior.CACHE_TARGETS[name] for name in ('api27', 'api28')}
TARGET_NAMES = tuple(CACHE_TARGETS)
SOURCE_NAMES = tuple('qa/art_cache_profile_recovery/' + name for name in (
    'cache_contract.py', 'jdk_observation.py', 'build.py', 'run.py', 'pilot.py', 'bootstrap.py',
    'reviewed_adb.py', 'README.md', 'prior-evidence/JDK21_REFERENCE_MANIFEST.json',
    'prior-evidence/CACHE_BUILD_BLOCKED_REVIEW.json', 'prior-evidence/CACHE_NONCE_OBSERVATIONS.json',
    'prior-evidence/CACHE_BUILD_BLOCKED_RESULT.json', 'prior-evidence/RECOVERY_NONCE_LEDGER.json')) + (
        '.github/workflows/android-art-cache-profile-recovery.yml',)
JDK_SELECTION = {'distribution': 'temurin', 'java_version': '21.0.13+9.0.LTS', 'java_package': 'jdk',
                 'architecture': 'x64', 'check_latest': False, 'reference_manifest_sha256': REFERENCE_SHA}


def parent_lock(verify_sources=True):
    path = ROOT / 'qa/class_metadata_profile_recovery/lock.json'
    require(path.is_file() and not path.is_symlink() and digest(path) == PARENT_LOCK_SHA,
            'The published parent recovery lock changed')
    # Pure file checks only. The previous branch context guard is never called.
    return prior.load_lock(verify_sources=verify_sources)


def reference_java():
    path = HERE / 'prior-evidence/JDK21_REFERENCE_MANIFEST.json'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == 48905
            and digest(path) == REFERENCE_SHA, 'Historical full JDK provenance differs')
    original = json.loads(path.read_bytes())
    require(original.get('schema') == 'WAEX_CLASS_METADATA_ART_BUILD_V2'
            and original.get('run_id') == '45699162692' and original.get('attempt') == '1'
            and original.get('workflow_commit') == 'c26f330a3cbd5d26807f1b9358daa46a62d26f3a',
            'Historical JDK producer differs')
    java = original['kotlin_toolchain']['java']
    require(java.get('properties') == {'java.specification.version': '21', 'java.version': '21.0.13',
                'java.runtime.version': '21.0.13+9-LTS', 'java.vendor': 'Eclipse Adoptium'}
            and java.get('javac_version') == 'javac 21.0.13'
            and set(java.get('files_sha256', {})) ==
                {'bin/java', 'bin/javac', 'release', 'lib/modules', 'lib/ct.sym', 'lib/server/libjvm.so'},
            'Historical exact JDK identity is incomplete')
    return java


def previous_cache_not_executed():
    observed = json.loads((HERE / 'prior-evidence/CACHE_NONCE_OBSERVATIONS.json').read_bytes())
    blocked = json.loads((HERE / 'prior-evidence/CACHE_BUILD_BLOCKED_RESULT.json').read_bytes())
    require(observed.get('schema') == 'WAEX_ART_RECOVERY_CACHE_RECOGNIZED_CLAIMS_V1'
            and observed.get('run_id') == PRIOR_RUN and observed.get('head_sha') == BASE
            and observed.get('claims') == [] and observed.get('claim_count') == 0
            and observed.get('new_cache_Android_invocations_observed') == 0
            and observed.get('jobs', {}).get('cache', {}).get('conclusion') == 'skipped'
            and observed.get('jobs', {}).get('cache', {}).get('status') == 'completed',
            'Earlier cache workload absence is not bound to observed skipped jobs')
    require(blocked.get('schema') == 'WAEX_ART_CACHE_PROBE_BUILD_V1'
            and blocked.get('status') == 'BLOCKED'
            and blocked.get('producer') == {'workflow_commit': BASE, 'run_id': PRIOR_RUN, 'attempt': '1'}
            and blocked.get('error') == 'RuntimeError: Existing pinned tool differs: java'
            and blocked.get('canonical_workloads_executed') == 0 and blocked.get('android_executed') is False
            and 'probe' not in blocked, 'Earlier failed build no longer identifies the precompilation gate')
    return observed


def consumed_nonces(lock, *, inherited=None):
    inherited = parent_lock() if inherited is None else inherited
    old = set(prior.consumed_nonces(inherited))
    require(len(old) == 53, 'Expected preserved parent claim set differs')
    path = HERE / 'prior-evidence/RECOVERY_NONCE_LEDGER.json'
    expected = lock.get('recovery_nonce_ledger_sha256')
    require(type(expected) is str and re.fullmatch(r'[0-9a-f]{64}', expected)
            and path.is_file() and not path.is_symlink() and digest(path) == expected,
            'The final preceding-run nonce ledger is missing or differs')
    ledger = json.loads(path.read_bytes())
    require(ledger.get('schema') == 'WAEX_ART_RECOVERY_CONSUMED_CLAIMS_V1'
            and ledger.get('run_id') == PRIOR_RUN and ledger.get('head_sha') == BASE
            and ledger.get('attempt') == '1' and ledger.get('collection_complete') is True
            and ledger.get('prior_non_reusable_count') == 53
            and type(ledger.get('prior_non_reusable_nonces')) is list
            and len(ledger['prior_non_reusable_nonces']) == 53
            and set(ledger['prior_non_reusable_nonces']) == old
            and ledger.get('collisions') == [] and ledger.get('claim_collection_issues') == [],
            'Preceding-run claims were not completely and independently collected')
    claims = ledger.get('claims')
    require(type(claims) is list and type(ledger.get('claim_count')) is int
            and type(ledger.get('unique_claim_count')) is int
            and ledger['claim_count'] == ledger['unique_claim_count'] == len(claims)
            and all(type(row) is dict and row.get('reusable') is False
                    and row.get('consumed_or_reserved') is True
                    and row.get('target') in prior.RUNTIME_VARIANTS
                    and row.get('role') in ('phase', 'baseline', 'candidate')
                    and type(row.get('nonce')) is str and re.fullmatch(r'[0-9a-f]{32}', row['nonce'])
                    for row in claims), 'Recognized claim fields or counts differ')
    added = {row['nonce'] for row in claims}
    require(len(added) == len(claims) and not (added & old), 'Duplicate prior or new claim')
    combined = old | added
    values = lock.get('consumed_nonces')
    require(type(values) is list and len(values) == len(set(values)) == len(combined)
            and set(values) == combined and lock.get('known_non_reusable_count') == len(combined)
            and ledger.get('combined_known_unique_count') == len(combined),
            'The new cache-only exclusion set omits a consumed or reserved nonce')
    return frozenset(combined)


def load_lock(verify_sources=True):
    path = HERE / 'lock.json'
    require(path.is_file() and not path.is_symlink(), 'Cache-only lock missing or redirected')
    lock = json.loads(path.read_bytes())
    require(lock.get('schema') == 'WAEX_ART_CACHE_ONLY_RECOVERY_LOCK_V1'
            and lock.get('repository') == REPOSITORY and lock.get('ref') == REF
            and lock.get('base_commit') == BASE and lock.get('targets') == list(TARGET_NAMES)
            and lock.get('canonical_workload_invocations') == 0
            and lock.get('canonical_build_invocations') == 0
            and lock.get('parent_lock_sha256') == PARENT_LOCK_SHA, 'Cache-only admission differs')
    inherited = parent_lock(verify_sources=verify_sources)
    expected_inherited = {**inherited['inherited_source_sha256'], **inherited['source_sha256'],
                          'qa/class_metadata_profile_recovery/lock.json': PARENT_LOCK_SHA}
    require(lock.get('inherited_source_sha256') == expected_inherited
            and lock.get('build_tool_sha256') == inherited['build_tool_sha256']
            and lock.get('build_sdk_metadata_sha256') == inherited['build_sdk_metadata_sha256']
            and lock.get('historical_matrix_lock_sha256') == inherited['historical_matrix_lock_sha256'],
            'Preserved parent source, SDK or tool pins changed')
    require(set(lock.get('source_sha256', {})) == set(SOURCE_NAMES), 'Own source pin coverage differs')
    if verify_sources:
        for rel, expected in lock['source_sha256'].items():
            p = ROOT / rel
            require(re.fullmatch(r'(?:qa|\.github)/[A-Za-z0-9_./-]+', rel) and '..' not in Path(rel).parts
                    and re.fullmatch(r'[0-9a-f]{64}', expected) and p.is_file() and not p.is_symlink()
                    and digest(p) == expected, 'Pinned cache-only source differs: ' + rel)
    require(lock.get('jdk_selection') == JDK_SELECTION
            and lock.get('jdk_file_sha256') == reference_java()['files_sha256'],
            'The exact historical JDK selector or six-file identity differs')
    previous_cache_not_executed()
    consumed_nonces(lock, inherited=inherited)
    return lock


def context_check(env, *, verify_sources=True):
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REF') == REF and env.get('GITHUB_EVENT_NAME') == 'push',
            'Only the dedicated public cache-only push branch is admitted')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1'
            and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', ''))
            and re.fullmatch(r'[0-9a-f]{40}', env.get('GITHUB_SHA', '')),
            'Only one concrete first-attempt producer is admitted')
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_bytes())
    require(event.get('repository', {}).get('full_name') == REPOSITORY
            and event.get('repository', {}).get('private') is False
            and event.get('ref') == REF and event.get('after') == env['GITHUB_SHA']
            and event.get('deleted') is False and event.get('forced') is False,
            'Event does not bind the exact ordinary cache-only push')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'Only the isolated Linux x86_64 runner is admitted')
    return load_lock(verify_sources=verify_sources)


def checked_matrix(path, target):
    require(target in CACHE_TARGETS, 'A canonical workload profile cannot enter cache-only admission')
    return prior.checked_matrix(path, target)
