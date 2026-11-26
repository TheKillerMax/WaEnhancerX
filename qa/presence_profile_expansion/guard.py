"""Strict, new CI context for the fifteen still-unqualified Presence profiles."""
import hashlib
import json
from pathlib import Path
import platform
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = HERE / 'lock.json'
REPOSITORY = 'TheKillerMax/WaEnhancerX'
REF = 'refs/heads/lab/presence-profile-expansion-20261126'
BASE = '1e666077571c39896b7fcadbf7c549b440d51a86'
TARGET_NAMES = ('api27', 'api29', 'api30', 'api31', 'api32', 'api33', 'api35',
                'api36', 'api37', 'api36.1', 'api36-16k', 'api36.1-16k',
                'api37-16k', 'api37.1-16k', 'api37.2-16k')
QUALIFIED_EXCLUDED = ('api24', 'api25', 'api26', 'api28', 'api34', 'api35-16k')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_context(env, event, system, machine):
    require(env.get('GITHUB_ACTIONS') == 'true'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REF') == REF
            and env.get('GITHUB_EVENT_NAME') == 'push'
            and env.get('GITHUB_RUN_ATTEMPT') == '1'
            and not env.get('GITHUB_HEAD_REF'), 'Only the first push attempt on the reviewed new lab branch is allowed')
    sha = env.get('GITHUB_SHA', '')
    require(re.fullmatch(r'[0-9a-f]{40}', sha) is not None
            and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')) is not None,
            'A concrete workflow commit and run are required')
    repo = event.get('repository', {})
    require(repo.get('full_name') == REPOSITORY and repo.get('private') is False
            and event.get('ref') == REF and event.get('after') == sha
            and event.get('deleted') is False, 'Push event does not identify this public fork commit')
    require(system == 'Linux' and machine == 'x86_64', 'The reviewed job requires Linux x86_64')
    return {'repository': REPOSITORY, 'ref': REF, 'workflow_commit': sha,
            'run_id': env['GITHUB_RUN_ID'], 'attempt': '1'}


def checked_sources(root=ROOT):
    lock = json.loads((root / 'qa/presence_profile_expansion/lock.json').read_bytes())
    require(lock.get('schema') == 'WAEX_PRESENCE_PROFILE_LAB_V1'
            and lock.get('base_revision') == BASE and lock.get('lab_ref') == REF
            and lock.get('targets') == list(TARGET_NAMES)
            and lock.get('qualified_targets_excluded') == list(QUALIFIED_EXCLUDED),
            'New Presence profile lock identity differs')
    pins = lock.get('execution_sources', {})
    require(isinstance(pins, dict) and len(pins) >= 16
            and 'qa/presence_profile_expansion/guard.py' in pins
            and '.github/workflows/android-presence-profile-expansion.yml' in pins,
            'New execution source closure is incomplete')
    for relative, expected in pins.items():
        require(isinstance(relative, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', relative)
                and not relative.startswith('/') and '..' not in relative.split('/'),
                'Invalid pinned source path')
        path = root / relative
        require(not path.is_symlink() and path.is_file()
                and re.fullmatch(r'[a-f0-9]{64}', expected or '') is not None
                and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                'Frozen execution source differs: ' + relative)
    return lock


def context_check(env):
    path = Path(env.get('GITHUB_EVENT_PATH', '/missing/event'))
    require(path.is_file() and 0 < path.stat().st_size <= 2 * 1024**2, 'Bounded real event JSON required')
    value = verify_context(env, json.loads(path.read_bytes()), platform.system(), platform.machine())
    checked_sources()
    return value

