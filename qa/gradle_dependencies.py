"""Resolve fixture dependencies before compiling or running tests.

Only transient dependency transport failures may be retried, with the same
project, repositories and coordinates. The consumer runs once after
preparation succeeds; its requested offline/online mode stays unchanged. A
missing artifact, compiler error or assertion is never turned into a retry.
Every bounded attempt is retained.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

TASK = ':probe:waexPrepareDependencyCache'
MARKER = 'WAEX_DEPENDENCIES_PREPARED=1'
MAX_TIMEOUT_SECONDS = 600
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 15)
_ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_TASK = re.compile(r'^> Task (\S+)', re.M)
_RESOLUTION = re.compile(r'could not (?:resolve|GET|HEAD|download)|could not get resource|'
                         r'could not resolve all (?:files|artifacts)|'
                         r'failed to resolve', re.I)
_TRANSIENT = re.compile(r'(?:status|response) code[: ]+(?:429|5\d\d)\b|'
                        r'HTTP[^\n]*(?:429|5\d\d)\b|too many requests|'
                        r'connection (?:reset|timed out)|read timed out|'
                        r'unknownhostexception|sockettimeoutexception|'
                        r'temporary failure in name resolution', re.I)
_FATAL = re.compile(r'compilation (?:error|failed)|script compilation|'
                    r'could not compile|there were failing tests|assertionerror|'
                    r'dependency verification failed|checksum|signature|'
                    r'unauthorized|forbidden|authentication failed|authorization failed|'
                    r'(?:status|response) code[: ]+(?:401|403|404)\b', re.I)

# This task has no dependsOn relationship with compilation or tests. The graph
# guard rejects plugin-added task dependencies instead of running them repeatedly.
PREPARATION_TASK = r'''
tasks.register("waexPrepareDependencyCache") {
 notCompatibleWithConfigurationCache("Resolves this isolated fixture's classpaths")
 doLast {
  val required = listOf("debugCompileClasspath", "debugRuntimeClasspath",
    "debugUnitTestCompileClasspath", "debugUnitTestRuntimeClasspath")
  required.forEach { name ->
   val configuration = configurations.getByName(name)
   check(configuration.isCanBeResolved) { "Unresolvable required configuration: $name" }
   check(configuration.resolve().isNotEmpty()) { "Empty required configuration: $name" }
  }
  listOf("kotlinCompilerClasspath", "kotlinCompilerPluginClasspathDebug",
    "kotlinCompilerPluginClasspathDebugUnitTest", "androidApis", "androidJdkImage")
   .mapNotNull { configurations.findByName(it) }.filter { it.isCanBeResolved }
   .forEach { it.resolve() }
  println("WAEX_DEPENDENCIES_PREPARED=1")
 }
}
if (gradle.startParameter.taskNames == listOf(":probe:waexPrepareDependencyCache")) {
 gradle.taskGraph.whenReady {
  check(allTasks.map { it.path } == listOf(":probe:waexPrepareDependencyCache")) {
   "Dependency preparation must not execute compilation or tests"
  }
 }
}
'''


class GradleDependencyError(RuntimeError):
    """Preparation stopped; no consumer was admitted."""


def _pins(wrapper, project):
    files = [Path(__file__), wrapper, project/'settings.gradle.kts',
             project/'gradle.properties', project/'probe/build.gradle.kts']
    pins = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    # A checked-in launcher reads these on every invocation. Pin absence too,
    # so adding or replacing a wrapper distribution cannot change a retry.
    for name in ('gradle-wrapper.jar', 'gradle-wrapper.properties'):
        path = wrapper.parent/'gradle/wrapper'/name
        pins[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return pins


def _classification(content):
    text = _ANSI.sub('', content)
    tasks = _TASK.findall(text)
    forbidden = [name for name in tasks if name != TASK]
    complete = tasks == [TASK] and text.splitlines().count(MARKER) == 1
    retryable = (not forbidden and not _FATAL.search(text)
                 and bool(_RESOLUTION.search(text)) and bool(_TRANSIENT.search(text)))
    return complete, retryable, forbidden


def _stop(process):
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # The PID comes directly from the owned Popen instance, never external input.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def prepare_dependencies(wrapper, project, log, *, bash='bash', offline=False,
                         timeout=600, max_attempts=3):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError('Dependency preparation timeout must be in (0, 600] seconds')
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError('Dependency preparation requires 1..3 attempts')
    if type(offline) is not bool:
        raise ValueError('Offline selection must be Boolean')
    wrapper, project, log = Path(wrapper).resolve(), Path(project).resolve(), Path(log).absolute()
    inputs = _pins(wrapper, project)
    metadata = log.with_suffix('.json')
    if any(path.exists() or path.is_symlink() for path in (log, metadata)):
        raise ValueError('Use new preparation evidence paths; previous attempts are retained')
    command = [str(bash), wrapper.as_posix(), '-p', str(project), '--no-daemon',
               '--console=plain', '--no-configuration-cache', TASK]
    if offline:
        command.append('--offline')
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + timeout
    record = {'schema': 1, 'command': command, 'input_sha256': inputs, 'offline': offline,
              'timeout_seconds': timeout, 'max_attempts': 1 if offline else max_attempts,
              'attempts': [], 'accepted': False, 'consumer_runs': 0}

    def save():
        record['elapsed_seconds'] = round(time.monotonic()-started, 6)
        metadata.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')

    save()
    try:
        with log.open('x', encoding='utf-8') as aggregate:
            for number in range(1, record['max_attempts']+1):
                if _pins(wrapper, project) != inputs:
                    raise GradleDependencyError('Preparation inputs changed between attempts')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise GradleDependencyError('Dependency preparation exhausted its deadline')
                path = log.with_name(log.stem+'.attempt-'+str(number)+log.suffix)
                attempt = {'number': number, 'log': path.name, 'exit_code': None,
                           'timed_out': False, 'retryable': False}
                record['attempts'].append(attempt)
                with path.open('x', encoding='utf-8') as stream:
                    # Acquisition never prompts. Give Gradle a valid input handle
                    # even when a Windows automation parent has no console stdin.
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                               stdout=stream, stderr=subprocess.STDOUT,
                                               start_new_session=(os.name == 'posix'))
                    try:
                        attempt['exit_code'] = process.wait(timeout=max(.001, deadline-time.monotonic()))
                    except subprocess.TimeoutExpired:
                        attempt['timed_out'] = True
                        _stop(process)
                        attempt['exit_code'] = process.returncode
                    except BaseException:
                        _stop(process)
                        raise
                content = path.read_text(encoding='utf-8', errors='replace')
                aggregate.write(content)
                aggregate.flush()
                complete, retryable, forbidden = _classification(content)
                attempt.update(retryable=retryable, forbidden_tasks=forbidden,
                               complete=complete, log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                save()
                if _pins(wrapper, project) != inputs:
                    raise GradleDependencyError('Preparation inputs changed during execution')
                if attempt['exit_code'] == 0 and complete and not forbidden:
                    record['accepted'] = True
                    return record
                if (attempt['timed_out'] or not retryable or forbidden
                        or number == record['max_attempts'] or attempt['exit_code'] == 0):
                    raise GradleDependencyError('Dependency preparation failed; see '+str(path))
                delay = min(BACKOFF_SECONDS[number-1], max(0, deadline-time.monotonic()))
                if delay:
                    time.sleep(delay)
        raise GradleDependencyError('Dependency preparation did not complete')
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()
