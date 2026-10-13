#!/usr/bin/env python3
"""Run JDK regression tests against the production Dex cache (no Android device needed).

Java stubs are only used for Android/Xposed framework types; both cache classes
are compiled directly from the production source tree. This does NOT validate
native DexKit scanning, LSPosed injection or compatibility with future WhatsApp.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEX_SRC = ROOT / "app/src/main/java/com/waenhancer/xposed/core/devkit"
STUBS = {
    "androidx/annotation/NonNull.java": "package androidx.annotation; public @interface NonNull {}\n",
    "androidx/annotation/Nullable.java": "package androidx.annotation; public @interface Nullable {}\n",
    "android/os/SystemClock.java": "package android.os; public final class SystemClock { public static volatile long now; public static long elapsedRealtime() { return now; } }\n",
    "android/content/pm/PackageInfo.java": "package android.content.pm; public class PackageInfo { public long code; public long getLongVersionCode() { return code; } }\n",
    "android/content/pm/PackageManager.java": "package android.content.pm; public class PackageManager { public final PackageInfo info = new PackageInfo(); public PackageInfo getPackageInfo(String pkg, int flags) { return info; } }\n",
    "android/content/SharedPreferences.java": """package android.content;
public interface SharedPreferences {
  String getString(String name, String fallback);
  long getLong(String name, long fallback);
  Editor edit();
  interface Editor { Editor clear(); Editor putString(String key, String val);
     Editor putLong(String key, long val); void apply(); }
}
""",
    "android/content/Context.java": """package android.content;
import android.content.pm.PackageManager;
public abstract class Context {
  public static final int MODE_PRIVATE = 0;
  public abstract Context getApplicationContext();
  public abstract PackageManager getPackageManager();
  public abstract String getPackageName();
  public abstract SharedPreferences getSharedPreferences(String name, int mode);
}
""",
    "de/robv/android/xposed/XposedBridge.java": """package de.robv.android.xposed;
public class XposedBridge { public static void log(String text) {} }
""",
    "de/robv/android/xposed/XposedHelpers.java": """package de.robv.android.xposed;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
public final class XposedHelpers {
  public static Class<?> findClass(String name, ClassLoader loader) {
    try { return Class.forName(name, false, loader); }
    catch (ClassNotFoundException e) { throw new IllegalStateException(e); }
  }
  public static Method findMethodExact(Class<?> cls, String name, Class<?>... args) {
    try { return cls.getDeclaredMethod(name, args); }
    catch (ReflectiveOperationException e) { throw new IllegalStateException(e); }
  }
  public static Field findField(Class<?> cls, String name) {
    try { return cls.getDeclaredField(name); }
    catch (ReflectiveOperationException e) { throw new IllegalStateException(e); }
  }
}
""",
}
with tempfile.TemporaryDirectory(prefix="waex_dex_cooldown_") as directory:
    root = Path(directory)
    sources = []
    for path, contents in STUBS.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents)
        sources.append(str(file))
    sources.extend(map(str, [
        DEX_SRC / "DexNegativeLookupCache.java",
        DEX_SRC / "DexCacheManager.java",
        ROOT / "qa/TestDexNegativeLookupCache.java",
        ROOT / "qa/TestDexCacheManager.java",
    ]))
    subprocess.run(["javac", "--release", "17", "-d", str(root), *sources], check=True)
    for test in ["TestDexNegativeLookupCache", "TestDexCacheManager"]:
        subprocess.run(["java", "-cp", str(root),
                        "com.waenhancer.xposed.core.devkit." + test], check=True)

manager = (DEX_SRC / "DexCacheManager.java").read_text()
engine = (DEX_SRC / "DexSearchEngine.java").read_text()
assert manager.count("mFailedKeys.shouldSkip(") == 3
assert manager.count("mFailedKeys.recordFailure(") == 3
assert manager.count("mFailedKeys.clearFailure(") == 6
assert "mFailedKeys.clear();" in manager
assert "SystemClock.elapsedRealtime()" in manager
assert "new DexNegativeLookupCache(FAILED_RETRY_MS, MAX_FAILED_KEYS)" in manager
assert "mPrefs.edit().clear().putLong(\"host_version_code\"" in manager
assert "findMethodWithCache(" in engine and "findClassWithCache(" in engine
assert "mFailedKeys.contains(" not in manager
print("PASS: 9 DexKit/cache integration invariants")
