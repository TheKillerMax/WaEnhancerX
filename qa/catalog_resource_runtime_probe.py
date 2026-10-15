#!/usr/bin/env python3
"""Read pinned public module APK resources with Android 14 via Robolectric.

Runs the unmodified production catalog validation method, not the whole app.
No WhatsApp APK, licensing sources, signing keys, installation or LSPosed.
"""
import argparse,hashlib,json,os,subprocess,urllib.request,zipfile
from pathlib import Path
POM='''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<groupId>org.waex.qa</groupId><artifactId>catalog-qa</artifactId><version>1</version>
<repositories><repository><id>google</id><url>https://maven.google.com</url></repository></repositories>
<dependencies><dependency><groupId>org.robolectric</groupId><artifactId>robolectric</artifactId><version>4.17</version></dependency>
<dependency><groupId>org.robolectric</groupId><artifactId>android-all</artifactId><version>14-robolectric-10818077</version></dependency>
<dependency><groupId>junit</groupId><artifactId>junit</artifactId><version>4.13.2</version></dependency></dependencies></project>'''
PINNED={'debug':'c4531d92851c5f251614e8af822f340737981adeb7128341463f8897e3d42114','release':'f19d64239b493785b48540dce068a32a295f33bd33b18e48b46d168896c4ac0f'}
TEST='''import android.app.Application
import android.content.Context
import android.content.ContextWrapper
import android.content.res.AssetManager
import android.content.res.Configuration
import android.content.res.Resources
import android.util.DisplayMetrics
import java.util.Locale
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

data class PreferenceGroup(val id:String,val tabId:String)
data class FeatureItem(val key:String)
object ProductionValidator {
METHOD
fun verify(context:Context, extra:Boolean=false) = validateLocalizedResources(context, GROUPS,
    if(extra) FEATURES+FeatureItem("waex_qa_nonexistent") else FEATURES)
val GROUPS=listOf(GROUPS_LIST)
val FEATURES=listOf(FEATURES_LIST)
val NAMES=listOf(NAMES_LIST)
}
@RunWith(RobolectricTestRunner::class)
@Config(sdk=[34],manifest=Config.NONE,application=Application::class)
class CatalogResourcesTest {
private val locales=listOf("en","es-CL","ar","pt","id","ru","tr","hi","ur","de","fr")
private fun resourceContext(variant:String,tag:String,wrongPackage:Boolean=false):Context {
 val assets=AssetManager::class.java.getDeclaredConstructor().newInstance()
 val cookie=AssetManager::class.java.getDeclaredMethod("addAssetPath",String::class.java)
    .invoke(assets,System.getProperty("waex.apks")+"/"+variant+".apk") as Int
 assertTrue("APK added",cookie>0)
 val configuration=Configuration().apply {setLocale(Locale.forLanguageTag(tag))}
 val resources=Resources(assets,DisplayMetrics().apply {setToDefaults()},configuration)
 return object:ContextWrapper(RuntimeEnvironment.getApplication()) {
  override fun getResources()=resources
  override fun getPackageName()=if(wrongPackage) "com.waex.qa.wrong" else "com.waenhancer"
  override fun getApplicationContext():Context=this
 }
}
private fun verifyVariant(variant:String) {
 for(tag in locales) {
  val context=resourceContext(variant,tag)
  ProductionValidator.verify(context)
  for(name in ProductionValidator.NAMES) {
   val id=context.resources.getIdentifier(name,"string",context.packageName)
   assertTrue("$variant $tag $name ID",id!=0)
   assertEquals("com.waenhancer",context.resources.getResourcePackageName(id))
   assertTrue("$variant $tag $name text",context.getString(id).isNotBlank())
  }
  val title=context.getString(context.resources.getIdentifier("feat_always_online_title","string",context.packageName))
  if(tag=="es-CL")assertEquals("Siempre en línea",title)
  if(tag=="en")assertEquals("Always Online",title)
  println("VALIDATED $variant $tag ${ProductionValidator.NAMES.size} compiled resource lookups")
 }
}
@Test fun debugCompiledResources()=verifyVariant("debug")
@Test fun republishedReleaseCompiledResources()=verifyVariant("release")
@Test fun missingRequiredResourceStillFails() {
 for(variant in listOf("debug","release")) {
  try {ProductionValidator.verify(resourceContext(variant,"es-CL"),true);fail("Missing key must fail")}
  catch(e:IllegalArgumentException) {
   assertEquals("Preference catalog references missing localized strings: feat_waex_qa_nonexistent_title, feat_waex_qa_nonexistent_desc",e.message)
  }
 }
}
@Test fun wrongResourcePackageStillFails() {
 for(variant in listOf("debug","release")) {
  try {ProductionValidator.verify(resourceContext(variant,"es-CL",true));fail("Wrong package must fail")}
  catch(e:IllegalArgumentException) {assertEquals(214,e.message!!.substringAfter(": ").split(", ").size)}
 }
}
}
'''
def run(cmd,log):
 with log.open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=600)
 print(log.name,p.returncode,flush=True)
 if p.returncode:print(log.read_text()[-15000:]);raise RuntimeError('Command failed')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path.cwd());ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 root=args.root.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False);evidence=out/'evidence';evidence.mkdir();deps=out/'deps';deps.mkdir();apks=out/'apks';apks.mkdir()
 assets=[]
 for variant,expected in PINNED.items():
  url=f'https://github.com/WaEnhancerX/WaEnhancerX/releases/download/2.0.3/WaEnhancerX-v2.0.3_{variant}.apk'
  with urllib.request.urlopen(url,timeout=60) as r:data=r.read(64*1024*1024+1)
  if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Asset changed: '+variant)
  p=apks/(variant+'.apk');p.write_bytes(data)
  with zipfile.ZipFile(p) as z:assets.append(z.read('assets/preference_catalog.json'))
 if assets[0]!=assets[1]:raise ValueError('Catalogs differ; review variants independently')
 groups=json.loads(assets[0]);keys=list(dict.fromkeys(k for g in groups for k in g['keys']))
 names=[n for k in keys for n in [f'feat_{k}_title',f'feat_{k}_desc']]+['sec_'+k for k in dict.fromkeys(g['id'] for g in groups)]+['catalog_tab_'+k for k in dict.fromkeys(g['tabId'] for g in groups)]
 if len(names)!=214:raise ValueError('Pinned catalog changed')
 source=(root/'app/src/main/java/com/waenhancer/config/FeatureCatalog.kt').read_text()
 method=source[source.index('    private fun validateLocalizedResources('):].rstrip()[:-1].rstrip()
 if not method.endswith('    }'):raise ValueError('Unsupported validator extraction')
 test=TEST.replace('METHOD',method).replace('GROUPS_LIST',','.join('PreferenceGroup('+json.dumps(g['id'])+','+json.dumps(g['tabId'])+')' for g in groups)).replace('FEATURES_LIST',','.join('FeatureItem('+json.dumps(k)+')' for k in keys)).replace('NAMES_LIST',','.join(json.dumps(n) for n in names))
 (evidence/'CatalogResourcesTest.kt').write_text(test)
 (out/'pom.xml').write_text(POM)
 run(['mvn','-B','-f',str(out/'pom.xml'),'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies','-DoutputDirectory='+str(deps)],evidence/'dependencies.log')
 for p in deps.glob('*.aar'):
  with zipfile.ZipFile(p) as z:
   for n in z.namelist():
    if n=='classes.jar' or(n.startswith('libs/') and n.endswith('.jar')):(deps/(p.stem+'-'+n.replace('/','_'))).write_bytes(z.read(n))
 cp=':'.join(str(p) for p in deps.glob('*.jar'))
 run(['kotlinc',str(evidence/'CatalogResourcesTest.kt'),'-jvm-target','17','-classpath',cp,'-include-runtime','-d',str(out/'test.jar')],evidence/'compile.log')
 opens=['java.base/java.lang','java.base/java.util','java.base/java.io','java.base/java.net','java.base/java.security','java.base/java.text','java.base/jdk.internal.access','java.desktop/java.awt.font','jdk.compiler/com.sun.tools.javac.api']
 run(['java',*[f'--add-opens={p}=ALL-UNNAMED' for p in opens],'-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2','-Dwaex.apks='+str(apks),'-cp',str(out/'test.jar')+':'+cp,'org.junit.runner.JUnitCore','CatalogResourcesTest'],evidence/'junit.log')
 text=(evidence/'junit.log').read_text()
 if 'OK (4 tests)' not in text or text.count('VALIDATED ')!=22:raise RuntimeError('Not all tests/locale contexts ran')
 (evidence/'result.json').write_text(json.dumps({'apk_sha256':PINNED,'validator_source_sha256':hashlib.sha256(source.encode()).hexdigest(),'validator_method_sha256':hashlib.sha256(method.encode()).hexdigest(),'junit_tests':4,'valid_apk_locale_contexts':22,'required_strings_per_context':214,'negative_contexts':4,'scope':'production validator body with framework Resources loaded from public APK; NOT full Application startup or LSPosed'},indent=2))
 (evidence/'dependency-sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in deps.iterdir() if p.is_file()},indent=2))
if __name__=='__main__':main()
