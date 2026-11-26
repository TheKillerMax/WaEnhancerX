#!/usr/bin/env python3
"""Share already resolved framework JARs within one CI run, attempt and source head.

This command never resolves or downloads dependencies. Both producer and consumer
verify the reviewed 36 framework JARs and three instrumented Android SDKs. The
complete native runtime remains required. Unknown, missing or changed bundle
files fail before HMA starts; a failed verification never triggers a network fallback.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat

LOCK = Path(__file__).with_name('framework_dependency_lock.json')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Expected a regular, non-symlink file: ' + str(path))


def identity(run_id, run_attempt, head_sha):
    if not re.fullmatch(r'[1-9][0-9]*', run_id) or not re.fullmatch(r'[1-9][0-9]*', run_attempt):
        raise ValueError('Expected explicit positive CI run and attempt identifiers')
    if not re.fullmatch(r'[0-9a-f]{40}', head_sha):
        raise ValueError('Expected an exact source commit SHA')
    return {'run_id': run_id, 'run_attempt': run_attempt, 'head_sha': head_sha}


def load_lock(path):
    regular(path)
    lock = json.loads(path.read_text(encoding='utf-8'))
    if lock.get('schema') != 1 or lock.get('robolectric') != '4.17' or lock.get('sdk_levels') != [24, 28, 34]:
        raise ValueError('Unsupported framework dependency lock')
    files = lock['files']
    keys = set()
    for item in files:
        name, directory = item['name'], item['directory']
        if directory not in ('deps', 'sdk-jars') or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.jar', name):
            raise ValueError('Unsafe dependency path')
        key = directory + '/' + name
        if key in keys or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
            raise ValueError('Duplicate dependency or invalid digest')
        if type(item['bytes']) is not int or item['bytes'] <= 0:
            raise ValueError('Invalid dependency size')
        if directory == 'sdk-jars':
            relative = PurePosixPath(item['maven_path'])
            if relative.is_absolute() or '..' in relative.parts or relative.name != name:
                raise ValueError('Unsafe SDK repository path')
        keys.add(key)
    if len(files) != 39 or sum(i['directory'] == 'deps' for i in files) != 36:
        raise ValueError('The complete framework and API 24/28/34 graph is required')
    if 'deps/nativeruntime-dist-compat-1.0.19.jar' not in keys:
        raise ValueError('The real native runtime must not be omitted')
    return files


def checked(path, item):
    regular(path)
    if path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
        raise ValueError('Dependency identity mismatch: ' + str(path))


def metadata(lock, files, origin):
    return {'schema': 1, 'lock_sha256': sha(lock), 'origin': origin,
            'files': {i['directory'] + '/' + i['name']: {
                'bytes': i['bytes'], 'sha256': i['sha256']} for i in files}}


def verify(bundle, lock, origin):
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError('Expected a real bundle directory')
    files = load_lock(lock)
    expected = metadata(lock, files, origin)
    actual_files = set()
    for path in bundle.rglob('*'):
        if path.is_symlink():
            raise ValueError('Bundle symlinks are not permitted: ' + str(path))
        if path.is_dir():
            if path.relative_to(bundle).as_posix() not in ('deps', 'sdk-jars'):
                raise ValueError('Unexpected bundle directory: ' + str(path))
        else:
            regular(path)
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != set(expected['files']) | {'bundle.json'}:
        raise ValueError('Bundle files differ from the complete reviewed graph')
    manifest = bundle / 'bundle.json'
    if json.loads(manifest.read_text(encoding='utf-8')) != expected:
        raise ValueError('Bundle manifest, lock or CI origin mismatch')
    for item in files:
        checked(bundle / item['directory'] / item['name'], item)
    return {'accepted': True, 'verified_files': len(files), 'total_bytes': sum(i['bytes'] for i in files),
            'manifest_sha256': sha(manifest), 'lock_sha256': sha(lock), 'origin': origin,
            'network_requests': 0, 'native_runtime_required': True}


def create(bundle, deps, maven_repo, lock, origin):
    files = load_lock(lock)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError('Refusing to overwrite an existing bundle')
    if deps.is_symlink() or not deps.is_dir() or maven_repo.is_symlink() or not maven_repo.is_dir():
        raise ValueError('Expected existing dependency and Maven directories')
    if {p.name for p in deps.glob('*.jar')} != {i['name'] for i in files if i['directory'] == 'deps'}:
        raise ValueError('Producer dependency JARs differ from the reviewed graph')
    sources = []
    for item in files:
        path = deps / item['name'] if item['directory'] == 'deps' else maven_repo / item['maven_path']
        checked(path, item)
        sources.append(path)
    bundle.mkdir(parents=True)
    for directory in ('deps', 'sdk-jars'):
        (bundle / directory).mkdir()
    for item, source in zip(files, sources):
        shutil.copyfile(source, bundle / item['directory'] / item['name'])
    (bundle / 'bundle.json').write_text(json.dumps(metadata(lock, files, origin), indent=2) + '\n', encoding='utf-8')
    return verify(bundle, lock, origin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('create', 'verify'))
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=LOCK)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--maven-repo', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-attempt', required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    origin = identity(args.run_id, args.run_attempt, args.head_sha)
    try:
        if args.mode == 'create':
            if args.deps is None or args.maven_repo is None:
                parser.error('create requires --deps and --maven-repo')
            result = create(args.bundle, args.deps, args.maven_repo, args.lock, origin)
        else:
            result = verify(args.bundle, args.lock, origin)
    except (ValueError, OSError, KeyError, TypeError) as failure:
        result = {'accepted': False, 'origin': origin, 'error': str(failure), 'network_requests': 0}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
