"""Build an audited Kotlin home from fixed Maven inputs for the Linux lab only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'toolchain-lock.json'
LIBRARIES = {
    'kotlin-compiler.jar', 'kotlin-stdlib.jar', 'kotlin-stdlib-jdk7.jar',
    'kotlin-stdlib-jdk8.jar', 'kotlin-script-runtime.jar', 'kotlin-reflect.jar',
    'trove4j.jar', 'kotlinx-coroutines-core-jvm.jar', 'annotations.jar',
}
JAVA_ENV_OPTIONS = (
    'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH',
    'JAVA_OPTS', 'KOTLIN_OPTS', 'KOTLIN_HOME', 'KOTLIN_RUNNER',
)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def checked_lock():
    lock = json.loads(LOCK.read_bytes())
    require(lock['schema'] == 'WAEX_CLASS_METADATA_KOTLIN_TOOLCHAIN_V1'
            and lock['kotlin_version'] == '2.0.20' and lock['java_major'] == 21,
            'Unexpected compiler lock')
    rows = lock['artifacts']
    require(len(rows) == len(LIBRARIES)
            and {row['file'] for row in rows} == LIBRARIES,
            'Compiler dependency closure differs')
    for row in rows:
        url = urllib.parse.urlsplit(row['url'])
        require(url.scheme == 'https' and url.netloc == 'repo.maven.apache.org'
                and url.path.startswith('/maven2/') and url.path.endswith('.jar')
                and not url.query and not url.fragment,
                'Compiler dependency URL outside Maven Central')
        require(type(row['bytes']) is int and 0 < row['bytes'] <= 80 * 1024**2
                and re.fullmatch('[a-f0-9]{64}', row['sha256']),
                'Invalid compiler dependency identity')
    return lock


def checked_payload(raw, row):
    require(len(raw) == row['bytes']
            and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Compiler dependency identity differs: ' + row['file'])
    return raw


def payload(row, cache=None):
    if cache is not None:
        path = Path(cache) / row['url'].rsplit('/', 1)[1]
        require(path.is_file() and not path.is_symlink(),
                'Missing regular compiler cache entry: ' + str(path))
        require(path.stat().st_size == row['bytes'], 'Compiler cache size differs')
        return checked_payload(path.read_bytes(), row)
    with urllib.request.urlopen(row['url'], timeout=45) as response:
        require(response.url == row['url'], 'Unexpected compiler download redirect')
        raw = response.read(row['bytes'] + 1)
    return checked_payload(raw, row)


def java_environment(java_home):
    java_home = Path(java_home).resolve(strict=True)
    require(sys.platform.startswith('linux'), 'This toolchain is for the Linux lab')
    java, javac = java_home / 'bin/java', java_home / 'bin/javac'
    require(all(p.is_file() and os.access(p, os.X_OK) for p in (java, javac)),
            'Selected JDK executables are missing')
    env = os.environ.copy()
    removed = [name for name in JAVA_ENV_OPTIONS if name in env]
    for name in JAVA_ENV_OPTIONS:
        env.pop(name, None)
    env['JAVA_HOME'] = str(java_home)
    env['PATH'] = str(java_home / 'bin') + os.pathsep + env.get('PATH', '')
    result = subprocess.run([str(java), '-XshowSettings:properties', '-version'],
                            stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=30, env=env)
    text = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    properties = dict(re.findall(r'^\s*(java\.[a-z.]+) = (.+)$', text, re.M))
    require(result.returncode == 0 and properties.get('java.specification.version') == '21'
            and Path(properties.get('java.home', '')).resolve() == java_home,
            'The selected Java runtime is not the requested JDK21')
    javac_result = subprocess.run([str(javac), '-version'], stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=30, env=env)
    javac_version = (javac_result.stdout + javac_result.stderr).decode().strip()
    require(javac_result.returncode == 0 and re.fullmatch(r'javac 21(?:\.[^\s]+)?', javac_version),
            'Selected javac is not version21')
    identity_files = [java, javac, java_home / 'release', java_home / 'lib/modules', java_home / 'lib/ct.sym',
                      java_home / 'lib/server/libjvm.so']
    require(all(path.is_file() for path in identity_files), 'Incomplete selected JDK21')
    receipt = {
        'java_home': str(java_home),
        'properties': {key: properties.get(key) for key in (
            'java.specification.version', 'java.version', 'java.runtime.version', 'java.vendor')},
        'javac_version': javac_version,
        'files_sha256': {str(path.relative_to(java_home)): digest(path) for path in identity_files},
        'cleared_environment_names': removed,
        'qualification': 'Observed preinstalled JDK21; no cross-patch binary reproducibility claim',
    }
    return java_home, env, receipt


def verify_home(home, lock, launcher_sha256):
    home = Path(home)
    expected = {'lib/' + row['file'] for row in lock['artifacts']} | {'bin/kotlinc'}
    entries = list(home.rglob('*'))
    require(not any(path.is_symlink() for path in entries), 'Compiler home contains a symlink')
    require({path.relative_to(home).as_posix() for path in entries if path.is_file()} == expected,
            'Compiler home contains missing or unexpected files')
    for row in lock['artifacts']:
        path = home / 'lib' / row['file']
        require(path.stat().st_size == row['bytes'] and digest(path) == row['sha256'],
                'Compiler home identity differs: ' + row['file'])
    require(digest(home / 'bin/kotlinc') == launcher_sha256, 'Compiler launcher changed')


def prepare(out, java_home, cache=None):
    lock = checked_lock()
    java_home, env, java_receipt = java_environment(java_home)
    home = Path(out) / 'kotlin-2.0.20'
    home.mkdir(exist_ok=False)
    (home / 'lib').mkdir()
    (home / 'bin').mkdir()
    for row in lock['artifacts']:
        (home / 'lib' / row['file']).write_bytes(payload(row, cache))
    # The unchanged receipt runner uses lib/*.jar. This home contains only the
    # pinned compiler closure, without bundled plugins or other distributions.
    classpath = os.pathsep.join(str(home / 'lib' / row['file']) for row in lock['artifacts'])
    command = [str(java_home / 'bin/java'), '-Xmx512M', '-Xms128M',
               '--add-opens=java.base/java.util=ALL-UNNAMED',
               '-Dkotlin.home=' + str(home), '-cp', classpath,
               'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-kotlin-home', str(home)]
    launcher = home / 'bin/kotlinc'
    launcher.write_text('#!/usr/bin/env python3\nimport os, sys\ncommand = '
                        + repr(command) + '\nos.execv(command[0], command + sys.argv[1:])\n',
                        encoding='utf-8')
    launcher.chmod(0o755)
    launcher_sha256 = digest(launcher)
    verify_home(home, lock, launcher_sha256)
    result = subprocess.run([str(launcher), '-version'], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=45, env=env)
    version = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
    (Path(out) / 'kotlin-version.stdout.log').write_bytes(result.stdout)
    (Path(out) / 'kotlin-version.stderr.log').write_bytes(result.stderr)
    require(result.returncode == 0 and re.fullmatch(
        r'info: kotlinc-jvm 2\.0\.20 \(JRE 21(?:[.+][^)]*)?\)', version),
        'Kotlin compiler version/JRE differs: ' + version)
    receipt = {'schema': lock['schema'], 'lock_sha256': digest(LOCK),
               'helper_sha256': digest(Path(__file__)), 'kotlin_version_output': version,
               'artifacts': lock['artifacts'], 'launcher_sha256': launcher_sha256,
               'java': java_receipt}
    (Path(out) / 'kotlin-toolchain.json').write_text(json.dumps(receipt, indent=2) + '\n',
                                                 encoding='utf-8')
    return launcher, env, receipt


def verify_after_build(launcher, receipt):
    require(digest(LOCK) == receipt['lock_sha256']
            and digest(Path(__file__)) == receipt['helper_sha256'], 'Toolchain recipe changed')
    verify_home(Path(launcher).parents[1], checked_lock(), receipt['launcher_sha256'])
    java_home = Path(receipt['java']['java_home'])
    require(all(digest(java_home / rel) == pin for rel, pin in receipt['java']['files_sha256'].items()),
            'Selected JDK changed during build')
