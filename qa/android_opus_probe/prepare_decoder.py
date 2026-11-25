#!/usr/bin/env python3
"""Build the pinned Xiph libopus host decoder without installing it system-wide."""
import argparse
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import struct
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'decoder-lock.json'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_members(raw, lock):
    archive = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz')
    members = archive.getmembers()
    names = [member.name.rstrip('/') for member in members]
    require(len(members) == lock['source_entries'] and len(set(names)) == len(names)
            and sum(member.size for member in members) == lock['source_expanded_bytes'], 'Source archive coverage differs')
    for member in members:
        path = PurePosixPath(member.name)
        require(path.parts and path.parts[0] == lock['source_root'] and not path.is_absolute()
                and '..' not in path.parts and '\\' not in member.name
                and (member.isfile() or member.isdir()), 'Unsafe source archive entry')
    return archive, members


def run(out, label, command, cwd, env, timeout):
    started = time.monotonic()
    stdout = out / (label + '.stdout.log'); stderr = out / (label + '.stderr.log')
    with stdout.open('xb') as output, stderr.open('xb') as errors:
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=errors, timeout=timeout)
    receipt = {'command': list(map(str, command)), 'returncode': result.returncode,
               'seconds': round(time.monotonic() - started, 3),
               'stdout_sha256': sha(stdout.read_bytes()), 'stderr_sha256': sha(stderr.read_bytes())}
    (out / (label + '.command.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    require(result.returncode == 0, label + ' failed; see preserved logs')
    require(stdout.stat().st_size + stderr.stat().st_size <= 16 * 1024**2, 'Build diagnostic bound')
    return receipt


def prepare(out, source_archive=None):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    recipe_paths = {'qa/android_opus_probe/prepare_decoder.py': Path(__file__),
                    'qa/android_opus_probe/decoder-lock.json': LOCK}
    recipe_pins = {name: sha(path.read_bytes()) for name, path in recipe_paths.items()}
    lock = json.loads(LOCK.read_bytes())
    require(lock['schema'] == 'WAEX_OPUS_HOST_DECODER_LOCK_V1' and lock['version'] == '1.5.2', 'Decoder lock version')
    require(platform.system() == 'Linux' and platform.machine() in ('x86_64', 'amd64'), 'Linux x86_64 host required')
    if source_archive is None:
        with urllib.request.urlopen(lock['source_url'], timeout=45) as response:
            final = urllib.parse.urlsplit(response.url)
            require(final.scheme == 'https' and final.netloc in ('downloads.xiph.org', 'ftp.osuosl.org')
                    and final.path.endswith('/opus-1.5.2.tar.gz'), 'Unexpected Xiph download redirect')
            raw = response.read(lock['source_bytes'] + 1)
    else:
        path = Path(source_archive)
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == lock['source_bytes'], 'Source archive file bound')
        raw = path.read_bytes()
    require(len(raw) == lock['source_bytes'] and sha(raw) == lock['source_sha256'], 'Xiph release checksum differs')
    (out / 'opus-1.5.2.tar.gz').write_bytes(raw)
    archive, members = safe_members(raw, lock)
    tree = out / 'source'; tree.mkdir()
    source_pins = {}
    with archive:
        for member in members:
            path = tree / member.name
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                body = archive.extractfile(member).read()
                with path.open('xb') as stream:
                    stream.write(body)
                path.chmod(member.mode & 0o755)
                os.utime(path, (member.mtime, member.mtime))
                source_pins[member.name] = sha(body)
    source = tree / lock['source_root']
    require(sha((source / 'COPYING').read_bytes()) == lock['license_sha256']
            and sha((source / 'configure').read_bytes()) == lock['configure_sha256'], 'Recipe/license identity')
    require((source / 'package_version').read_bytes() == b'PACKAGE_VERSION="1.5.2"\n'
            and not (source / '.git').exists() and not (source / 'update_version').exists(), 'Expected release version source')
    env = os.environ.copy()
    cleared = []
    for name in ('CC', 'CXX', 'CFLAGS', 'CPPFLAGS', 'LDFLAGS', 'AR', 'RANLIB', 'LD', 'AS',
                 'CPATH', 'LIBRARY_PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'CONFIG_SITE', 'MAKEFLAGS'):
        if name in env:
            cleared.append(name); env.pop(name)
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', CFLAGS=lock['cflags'], SOURCE_DATE_EPOCH='1712880000')
    tools = {}
    for name in ('cc', 'make', 'ar', 'ranlib', 'as', 'ld'):
        found = shutil.which(name, path=env['PATH']); require(found is not None, 'Missing host tool: ' + name)
        path = Path(found).resolve()
        result = subprocess.run([str(path), '--version'], capture_output=True, timeout=15, env=env)
        require(result.returncode == 0, 'Cannot identify host tool: ' + name)
        tools[name] = {'path': str(path), 'sha256': sha(path.read_bytes()),
                       'version': (result.stdout + result.stderr).decode(errors='replace').splitlines()[0]}
    env['CC'] = tools['cc']['path']; env['AR'] = tools['ar']['path']; env['RANLIB'] = tools['ranlib']['path']
    build = out / 'build'; build.mkdir()
    configure = run(out, 'configure', ['/bin/sh', source / 'configure', *lock['configure_flags']], build, env, 180)
    compiled = run(out, 'make', [tools['make']['path'], '-j2', 'libopus.la'], build, env, 420)
    products = [path for path in (build / '.libs').glob('libopus.so.*') if path.is_file() and not path.is_symlink()]
    require(len(products) == 1, 'Decoder shared library output ambiguous')
    body = products[0].read_bytes()
    require(0 < len(body) <= 16 * 1024**2 and body[:6] == b'\x7fELF\x02\x01'
            and struct.unpack_from('<H', body, 18)[0] == 62, 'Decoder ELF architecture/bound')
    artifact = out / 'artifact'; artifact.mkdir()
    library = artifact / 'libopus.so'; library.write_bytes(body); library.chmod(0o444)
    codec = ctypes.CDLL(str(library)); codec.opus_get_version_string.restype = ctypes.c_char_p
    version = codec.opus_get_version_string().decode('ascii')
    require(version == 'libopus 1.5.2', 'Built host decoder version differs')
    codec.opus_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    codec.opus_decoder_create.restype = ctypes.c_void_p
    codec.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
    codec.opus_decoder_destroy.restype = None
    error = ctypes.c_int(-1); state = codec.opus_decoder_create(48000, 1, ctypes.byref(error))
    require(bool(state) and error.value == 0, 'Decoder create control failed')
    codec.opus_decoder_destroy(state)
    require(all(sha((tree / name).read_bytes()) == pin for name, pin in source_pins.items()), 'Original source changed during build')
    require(sha(library.read_bytes()) == sha(body), 'Decoder changed during load control')
    require(all(sha(recipe_paths[name].read_bytes()) == pin for name, pin in recipe_pins.items()),
            'Decoder recipe changed during build')
    license_body = (source / 'COPYING').read_bytes()
    (artifact / 'COPYING').write_bytes(license_body)
    receipt = {'schema': 'WAEX_OPUS_HOST_DECODER_BUILD_V1', 'status': 'PASS_HOST_DECODER_BUILD',
               'source': lock, 'lock_sha256': sha(LOCK.read_bytes()), 'helper_sha256': sha(Path(__file__).read_bytes()),
               'source_sha256': recipe_pins,
               'library': {'name': library.name, 'bytes': len(body), 'sha256': sha(body), 'version': version},
               'license': {'file': 'COPYING', 'bytes': len(license_body), 'sha256': sha(license_body)},
               'license_text': license_body.decode('utf-8'), 'tools': tools,
               'cleared_environment_names': cleared, 'configure': configure, 'make': compiled,
               'source_files': source_pins, 'original_sources_unchanged': True,
               'workflow_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'scope': 'Host decoder build/create/destroy control; no Android or production application execution'}
    (artifact / 'decoder-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path)
    args = parser.parse_args()
    receipt = prepare(args.out, args.source_archive)
    print(json.dumps({'status': receipt['status'], 'library': receipt['library']}))


if __name__ == '__main__':
    main()
