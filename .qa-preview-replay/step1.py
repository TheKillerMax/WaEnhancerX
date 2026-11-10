from pathlib import Path
import re,runpy,pprint,subprocess
p=W/'app/src/main/java/com/waenhancer/xposed/features/media/MediaPreviewHook.kt'
s=p.read_text(encoding='utf-8'); assert len(re.findall(r'^<<<<<<<',s,re.M))==3
s=re.sub(r'<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> [^\n]*\n',lambda m:m[1],s,flags=re.S)
for old,new in [('waex_ui_full_quality_media_info_is_unavailable_a93af643','waex_ui_full_quality_media_info_is_unavailable'),('waex_ui_error_playing_video_14f39a6f','waex_ui_error_playing_video'),('waex_ui_unknown_preview_error_8c54371c','waex_ui_unknown_preview_error')]:s=s.replace(old,new)
assert not re.search(r'^(<<<<<<<|=======|>>>>>>>)',s,re.M)
p.write_text(s,encoding='utf-8');subprocess.run(['git','add',str(p)],cwd=W,check=True)
p=W/'qa/android_media_preview_test.py';s=p.read_text(encoding='utf-8')
s=s.replace("JAVA/'xposed/core/BaseFeature.kt', JAVA/'xposed/utils/HKDFv3.kt']", "JAVA/'xposed/core/BaseFeature.kt', JAVA/'xposed/utils/HKDFv3.kt',\n           JAVA/'xposed/core/HookRegistrar.java', JAVA/'xposed/core/ViewHookDispatcher.java']")
s=s.replace("with log.open('w')", "with log.open('w',encoding='utf-8')").replace('.read_text()',".read_text(encoding='utf-8')").replace('dest.write_text(content)',"dest.write_text(content,encoding='utf-8')")
s=s.replace("run([str(kotlin_compiler),", "run([*compiler_command,")
s=s.replace("kotlin_home, kotlin_compiler = find_kotlin()", "kotlin_home, kotlin_compiler = find_kotlin()\n    compiler_command=['java','-Dkotlin.home='+str(kotlin_home),'-cp',str(kotlin_home/'lib/*'),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-kotlin-home',str(kotlin_home)]")
needle="    test=ROOT/'qa/fixtures/media_preview/MediaPreviewLifecycleTest.java'"
s=s.replace(needle,"    lifecycle=[stage/p for p in SOURCES if p.suffix=='.java']\n    run(['javac','--release','17','-encoding','UTF-8','-cp',str(api_classes)+os.pathsep+api_cp,'-d',str(api_classes),*map(str,lifecycle)],out/'javac-real-http-lifecycle.log')\n    run(['javac','--release','17','-encoding','UTF-8','-cp',str(classes)+os.pathsep+cp,'-d',str(classes),*map(str,lifecycle)],out/'javac-lifecycle.log')\n"+needle)
p.write_text(s,encoding='utf-8')
p=W/'qa/fixtures/media_preview/runtime_doubles.py'; stubs=runpy.run_path(str(p))['STUBS']
q=R/'work/waex-pr87-current-20261109/qa/android_preserved_dispatch_test.py';ns=runpy.run_path(str(q))
for file,key in [('XposedBridge.java','XPOSED'),('XC_MethodHook.java','METHOD_HOOK'),('XposedHelpers.java','XPOSED_HELPERS')]:stubs['de/robv/android/xposed/'+file]=ns[key]
p.write_text('"""Explicit Android-external transport/host/Xposed boundaries; real BaseFeature/HookRegistrar/ViewHookDispatcher are compiled."""\nSTUBS = '+pprint.pformat(stubs,sort_dicts=False,width=110)+'\n',encoding='utf-8')
