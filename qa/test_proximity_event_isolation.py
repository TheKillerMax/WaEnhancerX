#!/usr/bin/env python3
"""JDK-only policy and source wiring checks; not a device sensor test."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "app/src/main/java/com/waenhancer/xposed/features/media"
hook = (src / "ProximitySensorHook.java").read_text(encoding="utf-8")
assert '"android.hardware.SystemSensorManager$SensorEventQueue"' in hook
assert '"mSensorsEvents"' in hook
assert 'candidate instanceof SensorEvent' in hook
assert 'ProximityEventPolicy.replaceNearWithFar(' in hook
assert 'sensor.getType(), sensor.getMaximumRange()' in hook
assert 'SENSOR_MAP_WARNING.compareAndSet(false, true)' in hook
assert 'values[0] = 100.0f' not in hook
assert '"android.hardware.SensorManager", classLoader' not in hook
assert 'isEnabled(PREF_KEY, false) || isEnabled("proximity_audios", false)' in hook
with tempfile.TemporaryDirectory() as temp:
    subprocess.run(['javac', '--release', '17', '-d', temp,
                    str(src/'ProximityEventPolicy.java'),
                    str(ROOT/'qa/TestProximityEventPolicy.java')], check=True)
    subprocess.run(['java', '-cp', temp,
                    'com.waenhancer.xposed.features.media.TestProximityEventPolicy'], check=True)
print('PASS: selective proximity mapping, no generic sensor corruption, original feature preferences retained')
