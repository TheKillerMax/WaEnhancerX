#!/usr/bin/env python3
"""Run unchanged public framework gates sequentially against one immutable source tree."""
import argparse
import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

SOURCE = 'c52f064bad7ba32445f8515bc2f0421618438975'
LAB_REF = 'refs/heads/lab/android-emulator-matrix-nightly8-20261124'
REPOSITORY = 'TheKillerMax/WaEnhancerX'
RATE_LIMIT = re.compile(r'(?:status(?:\s+code)?\s*[:=]?\s*429\b|HTTP(?:/\d(?:\.\d)?|\s+Error)\s+429\b|429\s+Too Many Requests|Too Many Requests)', re.I)
STAGES = ('source-and-tools', 'cache-verification', 'sdk-acquisition', 'maven-acquisition',
          'public-apks', 'presence-controls', 'presence', 'presence-companion',
          'store', 'dispatch', 'runtime', 'interface', 'stability', 'source-unchanged', 'cache-seal')
ALLOWED_DOWNLOAD_HOSTS = {'repo.maven.apache.org', 'github.com', 'release-assets.githubusercontent.com',
                          'objects.githubusercontent.com'}


class GateError(RuntimeError):
    pass


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(root, exclude=()):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise GateError('Symlink in dependency cache: ' + str(path))
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in exclude:
            result[relative] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    return result


def verify_cache(root, lock_sha):
    root.mkdir(parents=True, exist_ok=True)
    marker = root / 'verified-cache.json'
    actual = inventory(root, ('verified-cache.json',))
    if not marker.exists():
        if actual:
            raise GateError('Nonempty cache has no integrity manifest')
        return {'state': 'COLD', 'files': 0}
    expected = json.loads(marker.read_text())
    if expected.get('lock_sha256') != lock_sha or expected.get('files') != actual:
        raise GateError('Cache lock, file set, size or SHA256 differs')
    return {'state': 'VERIFIED_RESTORE', 'files': len(actual), 'manifest_sha256': digest(marker)}


def checked_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS or parsed.username or parsed.password:
        raise GateError('Unapproved dependency origin: ' + parsed.netloc)
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_artifact(path, spec):
    if not path.is_file() or path.is_symlink():
        raise GateError('Required regular dependency missing: ' + str(path))
    length = path.stat().st_size
    if length > spec['max_bytes'] or ('bytes' in spec and length != spec['bytes']):
        raise GateError('Dependency size differs: ' + path.name)
    if digest(path, spec['algorithm']) != spec['digest']:
        raise GateError('Dependency checksum differs: ' + path.name)


def acquire(spec, target, receipt, opener=None):
    """A verified hit performs no network I/O; a miss makes exactly one request chain."""
    if target.exists():
        verify_artifact(target, spec)
        receipt.update(state='VERIFIED_CACHE', bytes=target.stat().st_size, sha256=digest(target))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.partial')
    if partial.exists():
        raise GateError('Refusing stale partial download: ' + str(partial))
    receipt.update(state='REQUESTED', url=checked_url(spec['url']), attempts=1)
    opener = opener or urllib.request.build_opener(OfficialRedirect()).open
    try:
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'WAEX-public-QA-lab/1'})
        with opener(request, timeout=90) as response, partial.open('xb') as stream:
            receipt['http_status'] = response.status
            if response.status != 200:
                raise GateError('Unexpected HTTP status: ' + str(response.status))
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > spec['max_bytes']:
                    raise GateError('Dependency exceeded bounded size')
                stream.write(chunk)
        verify_artifact(partial, spec)
        partial.replace(target)
        receipt.update(state='VERIFIED_DOWNLOAD', bytes=total, sha256=digest(target))
    except urllib.error.HTTPError as exc:
        receipt.update(state='HTTP_FAILURE', http_status=exc.code, retry_after=exc.headers.get('Retry-After'))
        raise GateError(f'HTTP {exc.code}; no retry or mirror attempted') from exc
    except Exception as exc:
        receipt.update(state='FAILED', error=str(exc))
        raise
    finally:
        if partial.exists():
            partial.unlink()


def pom_contract(path):
    values = [n.value.value for n in ast.parse(path.read_text()).body
              if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'POM' for t in n.targets)
              and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
    if len(values) != 1:
        raise GateError('Expected one literal public POM: ' + str(path))
    xml = ET.fromstring(values[0]); ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
    coordinates = sorted(tuple(node.findtext('m:' + key, namespaces=ns) for key in ('groupId', 'artifactId', 'version'))
                         for node in xml.findall('m:dependencies/m:dependency', ns))
    return values[0], coordinates


def process_identity(pid):
    try:
        # comm can contain spaces or parentheses; fields following its last ')' start at state.
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return int(fields[1]), fields[19]
    except (OSError, ValueError, IndexError):
        return None


def proc_identities():
    identities = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdecimal():
            identity = process_identity(int(entry.name))
            if identity is not None:
                identities[int(entry.name)] = identity
    return identities


class ChildScope:
    """One sequential command scope; Linux adopts fast detached descendants here."""
    def __init__(self):
        if sys.platform != 'linux':
            raise GateError('Linux child-subreaper supervision is required')
        self.owner = os.getpid()
        self.owned = {}
        if any(parent == self.owner for parent, _ in proc_identities().values()):
            raise GateError('The sequential controller already has a child process')
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.prctl.restype = ctypes.c_int
        previous = ctypes.c_int()
        self.prctl(37, ctypes.addressof(previous))  # PR_GET_CHILD_SUBREAPER
        self.previous = previous.value
        self.prctl(36, 1)  # PR_SET_CHILD_SUBREAPER; Linux >=3.4
        self.active = True

    def prctl(self, option, value):
        code = self.libc.prctl(ctypes.c_int(option), ctypes.c_ulong(value),
                               ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0))
        if code != 0:
            number = ctypes.get_errno()
            raise OSError(number, 'prctl child-subreaper failed: ' + os.strerror(number))

    def discover(self):
        identities = proc_identities()
        changed = True
        while changed:
            changed = False
            for pid, (parent, started) in identities.items():
                parent_identity = identities.get(parent)
                ours = parent == self.owner or (parent_identity and self.owned.get(parent) == parent_identity[1])
                if ours and self.owned.get(pid) != started:
                    self.owned[pid] = started
                    changed = True
        return {pid: started for pid, started in self.owned.items()
                if identities.get(pid, (None, None))[1] == started}

    def close(self):
        if self.active:
            self.prctl(36, self.previous)
            self.active = False


def stop_owned(process, scope):
    """Drain only this command's identities, including adopted detached children."""
    deadline = time.monotonic() + 4
    sig = signal.SIGTERM
    while True:
        scope.discover()
        for pid, started in list(scope.owned.items()):
            identity = process_identity(pid)
            if identity and identity[1] == started:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        process.poll()  # Popen owns the direct child's wait status.
        for pid, started in list(scope.owned.items()):
            if pid != process.pid and process_identity(pid) == (scope.owner, started):
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        remaining = scope.discover()
        if not remaining:
            return {'method': 'linux_child_subreaper', 'owned_start_ticks': scope.owned,
                    'all_owned_processes_reaped': True}
        if time.monotonic() >= deadline:
            raise GateError('Owned process identities remain after cleanup: ' + str(sorted(remaining)))
        sig = signal.SIGKILL
        time.sleep(0.05)


def changed_log_rate_limit(watched, log, versions):
    for path in set(watched.rglob('*.log')) | {log}:
        try:
            if path.is_symlink():
                raise GateError('Symlinked process log is not accepted')
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            if versions.get(path) == identity:
                continue
            versions[path] = identity
            # Read the current file from byte zero. A rewritten/truncated log
            # cannot hide a 429 behind an offset left over from its predecessor.
            if stat.st_size > 16 * 1024**2:
                raise GateError('Process log exceeds 16 MiB: ' + str(path))
            with path.open('rb') as reader:
                data = reader.read(16 * 1024**2 + 1)
            if len(data) > 16 * 1024**2:
                raise GateError('Process log grew beyond its bounded read')
        except FileNotFoundError:
            continue
        found = RATE_LIMIT.search(data.decode('utf-8', errors='replace'))
        if found:
            return {'log': str(path), 'match': found.group(0)}
    return None


def run(command, cwd, env, log, watched, timeout=1200):
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {'command': list(map(str, command)), 'exit_code': None, 'http_429': None}
    started = time.monotonic()
    versions = {}
    process = scope = None
    try:
        scope = ChildScope()
        with log.open('w') as stream:
            process = subprocess.Popen(record['command'], cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            while True:
                scope.discover()
                limited = changed_log_rate_limit(watched, log, versions)
                if limited:
                    record['http_429'] = limited
                    raise GateError('HTTP429 observed; stopping owned stage without retry')
                code = process.poll()
                if code is not None:
                    record['exit_code'] = code
                    if code:
                        raise GateError('Stage process failed: ' + str(code))
                    return record
                if time.monotonic() - started > timeout:
                    raise GateError('Stage timeout')
                time.sleep(0.25)
    finally:
        cleanup_error = None
        late_error = None
        try:
            if process is not None:
                record['cleanup'] = stop_owned(process, scope)
                record['exit_code'] = process.returncode
                late_limit = changed_log_rate_limit(watched, log, versions)
                if late_limit:
                    record['http_429'] = late_limit
                    late_error = GateError('HTTP429 observed before completion; no retry')
        except Exception as exc:
            cleanup_error = exc
            record['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            if scope is not None:
                try:
                    scope.close()
                except Exception as exc:
                    cleanup_error = exc
                    record['subreaper_restore_error'] = str(exc)
            record['elapsed_seconds'] = round(time.monotonic() - started, 3)
            save(log.with_suffix('.command.json'), record)
        if cleanup_error is not None:
            raise GateError('Owned process cleanup was not verified') from cleanup_error
        if late_error is not None:
            raise late_error


def source_snapshot(root, expected=SOURCE):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    actual = git('rev-parse', 'HEAD').decode().strip()
    if actual != expected or git('status', '--porcelain', '--untracked-files=no').strip():
        raise GateError('Source checkout is not the exact clean reviewed commit')
    files = {}
    for item in git('ls-files', '-s', '-z').split(b'\0'):
        if not item:
            continue
        metadata, name = item.split(b'\t', 1); mode, blob, stage = metadata.decode().split()
        relative = name.decode(); path = root / relative
        if mode == '160000':
            files[relative] = {'mode': mode, 'gitlink': blob}
            continue
        if stage != '0' or path.is_symlink() or not path.is_file():
            raise GateError('Unexpected tracked path type/stage: ' + relative)
        executable = bool(path.stat().st_mode & 0o111)
        if executable != (mode == '100755'):
            raise GateError('Tracked executable mode differs: ' + relative)
        files[relative] = {'mode': mode, 'bytes': path.stat().st_size, 'sha256': digest(path)}
    return {'head': actual, 'files': files}


def junit_counts(folder, expected):
    reports = sorted(folder.glob('TEST-*.xml'))
    if not reports:
        raise GateError('Missing JUnit XML in ' + str(folder))
    counts = [0, 0, 0, 0]
    cases = 0
    for report in reports:
        suite = ET.parse(report).getroot()
        if suite.tag != 'testsuite':
            raise GateError('Unexpected JUnit root element')
        for i, key in enumerate(('tests', 'failures', 'errors', 'skipped')):
            counts[i] += int(suite.get(key, '0'))
        cases += len(suite.findall('testcase'))
        if suite.findall('.//testcase/failure') or suite.findall('.//testcase/error') or suite.findall('.//testcase/skipped'):
            raise GateError('JUnit testcase failure/error/skip')
    if counts != [expected, 0, 0, 0] or cases != expected:
        raise GateError('JUnit counts differ: ' + str((counts, cases)))
    return {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}


def validate_result(name, out):
    def read(relative):
        return json.loads((out / relative).read_text())
    if name == 'presence':
        result = read('results.json')
        mutations = {'wrong_dot_gravity', 'ignore_known_state', 'omit_dot_attachment'}
        if len(result) != 4 or {r['mutation'] for r in result if r['mutation']} != mutations:
            raise GateError('Incomplete focused renderer controls')
        positive = [r for r in result if r['mutation'] is None and r['baseline'] is False]
        if len(positive) != 1 or positive[0]['exit_code'] != 0:
            raise GateError('Renderer positive missing or failed')
        if any(r['unique_scenarios'] != 30 or r['sdk_levels'] != [28, 34, 36] for r in result):
            raise GateError('Renderer default API/scenario coverage differs')
        if any(r['exit_code'] == 0 for r in result if r['mutation']):
            raise GateError('Focused mutant survived')
        if not re.search(r'\bOK \(90 tests\)', (out / 'corrected/junit.log').read_text()):
            raise GateError('Missing 90 positive test verdict')
        return {'tests': 90, 'focused_mutants_rejected': 3, 'apis': [28, 34, 36]}
    if name == 'presence-companion':
        result = read('mutation-results.json')
        if len(result) != 15 or len({r['mutation'] for r in result}) != 15:
            raise GateError('Incomplete companion mutation set')
        if any(r['rejected_by_behavior'] is not True or r['android_api'] != 34 or
               r['unique_scenarios'] != 30 or r['oracle'] not in r['failures'] for r in result):
            raise GateError('Companion mutant not behaviorally rejected')
        return {'mutants_rejected': 15, 'scenarios_per_mutant': 30, 'api': 34}
    expected = {'store': 33, 'dispatch': 105, 'runtime': 12, 'interface': 12, 'stability': 15}[name]
    if name in ('store', 'dispatch'):
        result = read('result.json')
        if result['tests'] != expected or result['failures'] != 0 or result['accepted_result'] is not True:
            raise GateError('Preserved-store/dispatch acceptance differs')
        if result.get('expected_assertion_failures') != 0 or result.get('assertion_failures') != 0:
            raise GateError('Unexpected negative acceptance mode')
        return {'tests': expected, 'failures': 0}
    result = read('evidence/result.json')
    if any(result.get(k) != v for k, v in {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}.items()):
        raise GateError('Framework summary differs')
    if name == 'runtime' and (result.get('contexts') != 22 or result.get('locale_resource_tests') != 7):
        raise GateError('Runtime localization/context coverage differs')
    return junit_counts(out / 'evidence', expected)


class Lab:
    def __init__(self, source, cache, output, lock):
        self.source, self.cache, self.out = source.resolve(), cache.resolve(), output.resolve()
        if self.out.exists():
            raise GateError('Evidence output already exists')
        self.out.mkdir(parents=True)
        self.lock_path = lock.resolve(); self.lock = json.loads(lock.read_text()); self.lock_sha = digest(lock)
        self.result = {'status': 'RUNNING', 'source_head': SOURCE, 'lock_sha256': self.lock_sha,
                       'stages': {name: {'state': 'NOT_RUN'} for name in STAGES}, 'controller_retries': 0}
        self.env = {k: v for k, v in os.environ.items() if k not in
                    {'GITHUB_TOKEN', 'GH_TOKEN', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', 'JAVA_OPTS', 'MAVEN_ARGS', 'MAVEN_OPTS', 'GRADLE_OPTS'}}
        self.env.update(PYTHONDONTWRITEBYTECODE='1', GIT_NO_LAZY_FETCH='1',
                        GRADLE_USER_HOME=str(self.out / 'gradle-home'),
                        JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -Dorg.gradle.workers.max=2 '
                        '-Drobolectric.offline=true -Drobolectric.dependency.dir=' + str(self.cache / 'sdks'))

    def stage(self, name, action):
        row = self.result['stages'][name]; row['state'] = 'RUNNING'; save(self.out / 'result.json', self.result)
        try:
            row['evidence'] = action(); row['state'] = 'PASS'
        except Exception as exc:
            row.update(state='FAIL', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            save(self.out / 'result.json', self.result)

    def command(self, name, command, watched=None, timeout=1200):
        if shutil.disk_usage(self.out).free < 10 * 1024**3:
            raise GateError('Less than 10 GiB free on the isolated Linux runner')
        return run(command, self.source, self.env, self.out / 'logs' / (name + '.log'), watched or self.out / name, timeout)

    def preflight(self):
        if sys.platform != 'linux' or os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_REF') != LAB_REF:
            raise GateError('Only the isolated Linux lab branch is authorized')
        if self.lock['source_head'] != SOURCE or os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch'):
            raise GateError('Unexpected source lock or event')
        self.before = source_snapshot(self.source); save(self.out / 'source-before.json', self.before)
        wrapper = (self.source / 'gradle/wrapper/gradle-wrapper.properties').read_text()
        if 'distributionSha256Sum=' + self.lock['gradle']['sha256'] not in wrapper:
            raise GateError('Pinned Gradle wrapper checksum differs')
        tools = {}
        for name, args in {'java': ['-version'], 'javac': ['-version'], 'kotlinc': ['-version'], 'mvn': ['-version']}.items():
            found = shutil.which(name)
            if not found:
                raise GateError('Missing tool ' + name)
            path = Path(found).resolve(strict=True)
            self.command('version-' + name, [str(path), *args], timeout=60)
            text = (self.out / 'logs' / ('version-' + name + '.log')).read_text()
            tools[name] = {'path': str(path), 'sha256': digest(path), 'version_output': text}
        if 'kotlinc-jvm ' + self.lock['kotlin_cli_version'] not in tools['kotlinc']['version_output']:
            raise GateError('Preinstalled Kotlin CLI version differs from reviewed CI')
        if not re.search(r'version "21\.', tools['java']['version_output']):
            raise GateError('JDK21 required')
        kotlin_lib = Path(tools['kotlinc']['path']).parents[1] / 'lib'
        tools['kotlin_jars'] = inventory(kotlin_lib)
        android = Path(self.env.get('ANDROID_HOME', self.env.get('ANDROID_SDK_ROOT', ''))).resolve()
        self.aapt2 = android / 'build-tools/36.0.0/aapt2'
        for path in (self.aapt2, android / 'platforms/android-36/android.jar'):
            if not path.is_file():
                raise GateError('Required preinstalled SDK file missing: ' + str(path))
            tools[str(path)] = {'sha256': digest(path), 'bytes': path.stat().st_size}
        save(self.out / 'toolchain.json', tools)
        return {'head': SOURCE, 'tracked_entries': len(self.before['files']), 'toolchain': 'toolchain.json'}

    def cache_check(self):
        receipt = verify_cache(self.cache, self.lock_sha)
        for relative in ('wrapper', 'caches/modules-2'):
            source = self.cache / 'gradle' / relative
            if source.is_dir():
                shutil.copytree(source, self.out / 'gradle-home' / relative, dirs_exist_ok=True)
        return receipt

    def downloads(self, specs, directory):
        receipts = []
        try:
            for spec in specs:
                row = {'name': spec['name']}; receipts.append(row)
                acquire(spec, self.cache / directory / spec['name'], row)
        finally:
            save(self.out / (directory + '-acquisition.json'), receipts)
        return receipts

    def dependencies(self):
        paths = [self.source / 'qa' / name for name in ('android_preserved_store_test.py',
                  'android_preserved_dispatch_test.py', 'android_presence_row_test.py')]
        poms = [pom_contract(path) for path in paths]
        expected = sorted(tuple(c) for c in self.lock['maven_coordinates'])
        if any(coordinates != expected for _, coordinates in poms):
            raise GateError('Public runners no longer have the identical locked dependency closure')
        pom = self.out / 'public-fixture-pom.xml'; pom.write_text(poms[0][0])
        deps = self.cache / 'flat-deps'
        if not deps.exists():
            deps.mkdir(parents=True)
            settings = self.out / 'maven-settings.xml'
            settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"><mirrors/><servers/></settings>\n')
            self.command('maven-acquisition', ['mvn', '-B', '-C', '--no-transfer-progress', '-s', settings, '-gs', settings,
                         '-f', pom, '-Dmaven.repo.local=' + str(self.cache / 'maven'),
                         'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies',
                         '-DoutputDirectory=' + str(deps)], timeout=900)
        if not list(deps.glob('*.jar')):
            raise GateError('Empty cached compile dependency set')
        for archive in deps.glob('*.aar'):
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if name == 'classes.jar' or name.startswith('libs/') and name.endswith('.jar'):
                        target = deps / (archive.stem + '-' + name.replace('/', '_')); data = bundle.read(name)
                        if target.exists() and target.read_bytes() != data:
                            raise GateError('Extracted AAR cache differs')
                        target.write_bytes(data)
        native = self.lock['native_runtime']; verify_artifact(deps / native['name'], native)
        for spec in self.lock['small_jars']:
            verify_artifact(deps / spec['name'], spec)
        dexkit = self.lock['dexkit']; receipt = {}
        try:
            acquire(dexkit, self.cache / 'dexkit' / dexkit['name'], receipt)
        finally:
            save(self.out / 'dexkit-acquisition.json', receipt)
        with zipfile.ZipFile(self.cache / 'dexkit' / dexkit['name']) as bundle:
            jar = bundle.read('classes.jar')
        if hashlib.sha256(jar).hexdigest() != self.lock['dexkit_classes_sha256']:
            raise GateError('DexKit classes identity differs')
        (self.cache / 'dexkit/classes.jar').write_bytes(jar)
        save(self.out / 'compile-dependencies.json', inventory(deps))
        return {'single_resolution': True, 'coordinates': expected, 'files': len(list(deps.iterdir()))}

    def suite(self, name):
        py = sys.executable; qa = self.source / 'qa'; out = self.out / name
        deps, sdks = self.cache / 'flat-deps', self.cache / 'sdks'
        if name == 'presence-controls':
            command = [py, qa / 'test_presence_runner_controls.py']
        elif name == 'presence':
            command = [py, qa / 'android_presence_row_test.py', '--out', out, '--deps', deps,
                       '--sdk-dir', sdks, '--aapt2', self.aapt2, '--mutations']
        elif name == 'presence-companion':
            command = [py, qa / 'mutate_presence_rows.py', out, deps, '--sdk-dir', sdks, '--aapt2', self.aapt2]
        elif name in ('store', 'dispatch'):
            command = [py, qa / ('android_preserved_' + name + '_test.py'), '--out', out, '--deps', deps, '--sdk-jars', sdks]
            if name == 'dispatch':
                command.extend(['--dexkit', self.cache / 'dexkit/classes.jar'])
        else:
            filename = {'runtime': 'verify_runtime_framework.py', 'interface': 'verify_interface_scale_framework.py',
                        'stability': 'verify_stability_framework.py'}[name]
            command = [py, qa / filename, '--root', self.source, '--out', out]
            if name == 'runtime':
                command.extend(['--public-apk-cache', self.cache / 'public-apks'])
        self.command(name, command, out, timeout=1800 if name == 'presence-companion' else 1200)
        if name == 'presence-controls':
            log = (self.out / 'logs/presence-controls.log').read_text()
            if not re.search(r'Ran 19 tests?\b', log) or not re.search(r'^OK\s*$', log, re.M):
                raise GateError('Expected all 19 public runner controls')
            return {'controls': 19}
        return validate_result(name, out)

    def unchanged(self):
        after = source_snapshot(self.source); save(self.out / 'source-after.json', after)
        if after != self.before:
            raise GateError('The source checkout changed while testing')
        return {'tracked_entries': len(after['files']), 'identical': True}

    def seal_cache(self):
        gradle = self.cache / 'gradle'
        if gradle.exists():
            shutil.rmtree(gradle)
        for relative in ('wrapper', 'caches/modules-2'):
            source = self.out / 'gradle-home' / relative
            if source.is_dir():
                shutil.copytree(source, gradle / relative,
                                ignore=shutil.ignore_patterns('*.lock', 'gc.properties', '*.lck', '*.tmp'))
        files = inventory(self.cache, ('verified-cache.json',))
        save(self.cache / 'verified-cache.json', {'lock_sha256': self.lock_sha, 'source_head': SOURCE, 'files': files})
        shutil.copy2(self.cache / 'verified-cache.json', self.out / 'cache-manifest.json')
        return {'files': len(files), 'bytes': sum(v['bytes'] for v in files.values())}

    def execute(self):
        try:
            self.stage('source-and-tools', self.preflight)
            self.stage('cache-verification', self.cache_check)
            self.stage('sdk-acquisition', lambda: self.downloads(self.lock['sdks'], 'sdks'))
            self.stage('maven-acquisition', self.dependencies)
            self.stage('public-apks', lambda: self.downloads(self.lock['public_apks'], 'public-apks'))
            for name in STAGES[5:13]:
                self.stage(name, lambda name=name: self.suite(name))
            self.stage('source-unchanged', self.unchanged)
            self.stage('cache-seal', self.seal_cache)
            self.result['status'] = 'PASS'
        except Exception as exc:
            self.result.update(status='FAIL', error=type(exc).__name__ + ': ' + str(exc))
            if hasattr(self, 'before') and self.result['stages']['source-unchanged']['state'] == 'NOT_RUN':
                try:
                    self.stage('source-unchanged', self.unchanged)
                except Exception as integrity_error:
                    self.result['source_integrity_error'] = str(integrity_error)
            for row in self.result['stages'].values():
                if row['state'] == 'NOT_RUN':
                    row.update(state='BLOCKED', reason='Earlier stage failed; no retries or reduced tests')
        finally:
            save(self.out / 'result.json', self.result)
        return 0 if self.result['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('source_framework_lab_lock.json'))
    args = parser.parse_args()
    return Lab(args.source, args.cache, args.out, args.lock).execute()


if __name__ == '__main__':
    sys.exit(main())
