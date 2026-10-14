#!/usr/bin/env python3
"""Ensure Styles proximity switch writes the actual sensor hook preference."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'app/src/main/java/com/waenhancer'
screen=(root/'ui/screens/settings/StylesSettingsScreen.kt').read_text()
catalog=(root/'config/FeatureCatalog.kt').read_text()
policy=(root/'xposed/features/media/ProximityEventPolicy.java').read_text()
hook=(root/'xposed/features/media/ProximitySensorHook.java').read_text()
schema=(root/'config/PreferenceSchema.java').read_text()
assert '"disable_sensor_proximity", Type.BOOLEAN' in schema
assert 'private static final String PREF_KEY = "disable_sensor_proximity"' in hook
assert 'isEnabled(PREF_KEY, false)' in hook
assert '"disable_sensor_proximity"' in screen
assert 'StyleItem("Disable Screen off on proximity sensor"' in screen
assert '"Disable Screen off on proximity sensor", "Disable Screen off on proximity sensor to the whole WhatsApp", "disable_sensor_proximity"' in screen
assert '"miscellaneous_enhancements"' not in screen
assert 'FeatureItem("disable_sensor_proximity", "Disable Screen off on proximity sensor"' in catalog
assert '"miscellaneous_enhancements" to "disable_sensor_proximity"' in catalog
assert 'sensorType != PROXIMITY_TYPE' in policy
assert 'sensor.getType()' in hook
print('PASS: 11 UI/catalog/schema/host sensor preference invariants')
