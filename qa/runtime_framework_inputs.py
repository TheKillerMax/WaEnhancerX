"""Use the verified CI framework bundle without changing Gradle module metadata.

The native runtime keeps its original Maven POM and exact locked JAR. Only that
coordinate uses the local exclusive repository. Robolectric consumes the three
verified SDKs offline. Other Gradle dependencies retain their existing sources.
"""
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from framework_dependency_bundle import checked, identity, load_lock, sha, verify

QA = Path(__file__).resolve().parent
NATIVE = 'nativeruntime-dist-compat-1.0.19'
POM = QA / 'fixtures/dependencies' / (NATIVE + '.pom')
POM_PIN = {'bytes': 1334, 'sha256': 'd4918b9791ff87c4b7eb51beef56394d8b58e96a153318f978160d7807173173'}


def kotlin_string(value):
    return json.dumps(str(value), ensure_ascii=False).replace('$', r'\$')


def prepare(bundle, destination, run_id, run_attempt, head_sha, *,
            consumer='runtime', project='runtime-fixture', runner=None):
    consumers = {'runtime': ('runtime-fixture', 'verify_runtime_framework.py'),
                 'stability': ('stability-fixture', 'verify_stability_framework.py'),
                 'interface-scale': ('interface-scale-fixture', 'verify_interface_scale_framework.py')}
    if type(consumer) is not str or consumer not in consumers or project != consumers[consumer][0]:
        raise ValueError('Unknown or inconsistent framework consumer/project')
    expected_runner = QA / consumers[consumer][1]
    if runner is None and consumer != 'runtime':
        raise ValueError('An explicit runner is required for this framework consumer')
    runner = expected_runner if runner is None else Path(runner).resolve()
    if runner != expected_runner:
        raise ValueError('Framework consumer has a different executing runner')
    bundle, destination = Path(bundle).absolute(), Path(destination).absolute()
    lock = QA / 'framework_dependency_lock.json'
    origin = identity(run_id, run_attempt, head_sha)
    receipt = verify(bundle, lock, origin)
    checked(POM, POM_PIN)
    pom = ET.fromstring(POM.read_bytes())
    ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
    coordinates = [pom.findtext('m:' + key, namespaces=ns) for key in ('groupId', 'artifactId', 'version')]
    if coordinates != ['org.robolectric', 'nativeruntime-dist-compat', '1.0.19'] or pom.find('m:parent', ns) is not None or pom.findall('.//m:dependency', ns):
        raise ValueError('Original native-runtime metadata contract changed')
    native = next(row for row in load_lock(lock) if row['name'] == NATIVE + '.jar')
    repository = destination / 'native-repository'
    repository.mkdir(parents=True, exist_ok=False)
    module = repository / 'org/robolectric/nativeruntime-dist-compat/1.0.19'
    module.mkdir(parents=True)
    jar = module / (NATIVE + '.jar')
    try:
        os.link(bundle / 'deps' / native['name'], jar)
    except OSError:
        shutil.copyfile(bundle / 'deps' / native['name'], jar)
    checked(jar, native)
    shutil.copyfile(POM, module / POM.name)
    checked(module / POM.name, POM_PIN)
    record = {
        'schema': 'WAEX_RUNTIME_FRAMEWORK_INPUTS_V1', 'bundle': receipt,
        'bundle_directory': str(bundle), 'repository_uri': repository.as_uri(),
        'native': native, 'pom': {**POM_PIN, 'file': POM.name,
            'source_url': 'https://repo.maven.apache.org/maven2/org/robolectric/nativeruntime-dist-compat/1.0.19/' + POM.name},
        'sdk_directory': str(bundle / 'sdk-jars'), 'sdk_resolution': 'offline',
        'source_sha256': {str(path.relative_to(QA.parent)).replace('\\', '/'): sha(path) for path in (
            runner, Path(__file__).resolve(), QA / 'framework_dependency_bundle.py', lock, POM)},
        'scope': 'Exact native module and three SDKs supplied locally; other Gradle dependencies are unchanged.'}
    if consumer != 'runtime':
        record.update(schema='WAEX_GRADLE_FRAMEWORK_INPUTS_V1', consumer=consumer,
                      project_name=project, runner=runner.relative_to(QA.parent).as_posix())
    return record


def settings(record):
    uri = kotlin_string(record['repository_uri'])
    return '''pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement {
 repositories {
  exclusiveContent {
   forRepository { maven { name = "waexVerifiedNativeRuntime"; url = uri(URI); metadataSources { mavenPom() } } }
   filter { includeVersion("org.robolectric", "nativeruntime-dist-compat", "1.0.19") }
  }
  google(); mavenCentral()
 }
}
rootProject.name=PROJECT_NAME
include(":probe")
'''.replace('uri(URI)', 'uri(' + uri + ')').replace('PROJECT_NAME', kotlin_string(record.get('project_name', 'runtime-fixture')))


def test_configuration(record, evidence):
    replacements = {
        'SDK_DIRECTORY': kotlin_string(Path(record['sdk_directory']).as_posix()),
        'NATIVE_SHA256': kotlin_string(record['native']['sha256']),
        'NATIVE_BYTES': str(record['native']['bytes']) + 'L',
        'RESOLUTION_RECEIPT': kotlin_string((Path(evidence) / 'gradle-native-resolution.json').as_posix()),
    }
    text = '''
tasks.withType<Test>().configureEach {
 systemProperty("robolectric.offline", "true")
 systemProperty("robolectric.dependency.dir", SDK_DIRECTORY)
 val testTask = this
 doFirst {
  val native = configurations.getByName("debugUnitTestRuntimeClasspath").incoming.artifactView {
   componentFilter {
    it is org.gradle.api.artifacts.component.ModuleComponentIdentifier &&
     it.group == "org.robolectric" && it.module == "nativeruntime-dist-compat"
   }
  }.artifacts.artifacts
  check(native.size == 1) { "Expected exactly one real native-runtime artifact" }
  val artifact = native.single()
  val component = artifact.id.componentIdentifier as org.gradle.api.artifacts.component.ModuleComponentIdentifier
  check(component.version == "1.0.19")
  fun sha256(file: File): String {
   val digest = MessageDigest.getInstance("SHA-256")
   file.inputStream().use { input ->
    val buffer = ByteArray(1024 * 1024)
    while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
   }
   return digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
  }
  val resolved = artifact.file
  val resolvedPin = sha256(resolved)
  check(resolved.length() == NATIVE_BYTES && resolvedPin == NATIVE_SHA256) { "Gradle resolved different native bytes" }
  // Match actual Test inputs by bytes, allowing a verified cache copy at another path.
  val used = testTask.classpath.files.filter { it.isFile && it.length() == NATIVE_BYTES }
   .map { it to sha256(it) }.filter { it.second == resolvedPin }
  check(used.size == 1) { "Expected the exact native-runtime bytes once on the Test classpath" }
  val (file, pin) = used.single()
  val receipt = mapOf("coordinate" to "${component.group}:${component.module}:${component.version}",
   "path" to file.absolutePath, "bytes" to file.length(), "sha256" to pin,
   "resolved_artifact_path" to resolved.absolutePath, "resolved_artifact_bytes" to resolved.length(),
   "resolved_artifact_sha256" to resolvedPin, "matched_test_classpath_files" to used.size,
   "on_test_classpath" to true, "sdk_directory" to SDK_DIRECTORY, "sdk_offline" to true)
  File(RESOLUTION_RECEIPT).writeText(groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(receipt)) + "\\n")
 }
}
'''
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def finish(record, evidence):
    evidence = Path(evidence)
    raw = json.loads((evidence / 'gradle-native-resolution.json').read_text())
    native = record['native']
    if raw['coordinate'] != 'org.robolectric:nativeruntime-dist-compat:1.0.19' or type(raw['bytes']) is not int or raw['bytes'] != native['bytes'] or raw['sha256'] != native['sha256'] or raw['sdk_offline'] is not True or Path(raw['sdk_directory']) != Path(record['sdk_directory']):
        raise ValueError('Actual Gradle native/SDK resolution receipt differs')
    if raw.get('on_test_classpath') is not True or type(raw.get('matched_test_classpath_files')) is not int or raw['matched_test_classpath_files'] != 1 or type(raw.get('resolved_artifact_bytes')) is not int or raw['resolved_artifact_bytes'] != native['bytes'] or raw.get('resolved_artifact_sha256') != native['sha256']:
        raise ValueError('Gradle artifact was not bound to the actual Test classpath')
    checked(Path(raw['path']), native)
    checked(Path(raw['resolved_artifact_path']), native)
    record['after_execution_bundle'] = verify(Path(record['bundle_directory']), QA / 'framework_dependency_lock.json', record['bundle']['origin'])
    record['gradle_native_resolution'] = raw
    record['accepted'] = True
    (evidence / 'framework-inputs.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
