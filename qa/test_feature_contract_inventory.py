#!/usr/bin/env python3
"""Smoke and synthetic-fixture regression for the read-only feature inventory."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_contract_inventory import inventory, markdown

base = Path(__file__).resolve().parents[1]
report = inventory(base)
assert report['catalog_count'] >= 90
assert report['schema_key_count'] >= 300
assert 0 <= report['not_in_schema'] <= report['catalog_count']
assert 0 <= report['without_direct_xposed_literal'] <= report['catalog_count']
assert any(x['key'] == 'hide_read_receipts' and x['runtime_direct_refs'] for x in report['features'])
assert any(x['key'] == 'custom_view_dpi' for x in report['features'])
assert len(report['features']) == len(set(x['key'] for x in report['features']))
assert '| UI key | Type | Xposed source references |' in markdown(report)
assert len(json.dumps(report)) > 5000

with tempfile.TemporaryDirectory(prefix='waex_feature_inventory_') as directory:
    root = Path(directory)
    java_root = root/'app/src/main/java/com/waenhancer'
    for rel, data in {
        'config/FeatureCatalog.kt': '''private const val ASSET_NAME = "preference_catalog.json"
private val canonicalGroupOverrides = mapOf(
)
.flatMap { it.items() }
.filter { item -> canonicalGroupOverrides[item.key]?.let { it == item.groupId } ?: true }
.distinctBy { it.key }
''',
        'config/PreferenceSchema.java': 'add(entries, "alpha", Type.BOOLEAN, Sensitivity.PUBLIC_SETTING, Store.PUBLIC);',
        'core/preferences/SettingsBackupCodec.kt': '"beta" to "alpha"',
        'xposed/features/AlphaHook.java': 'boolean yes = prefs.getBoolean("alpha", false);',
    }.items():
        file = java_root/rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data)
    asset = root/'app/src/main/assets/preference_catalog.json'
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text('[{"id":"test","tabIndex":1,"tabId":"privacy","keys":["alpha","beta"]}]')
    resources = root/'app/src/main/res/values/strings.xml'
    resources.parent.mkdir(parents=True, exist_ok=True)
    resources.write_text('''<resources>
      <string name="sec_test">Test group</string>
      <string name="catalog_tab_privacy">Privacy</string>
      <string name="feat_alpha_title">Alpha</string>
      <string name="feat_alpha_desc">Alpha description</string>
      <string name="feat_beta_title">Beta</string>
      <string name="feat_beta_desc">Beta description</string>
    </resources>''')
    found = inventory(root)
    assert found['catalog_count'] == 2
    assert found['schema_key_count'] == 1
    assert found['not_in_schema'] == 1
    assert found['without_direct_xposed_literal'] == 1
    alpha, beta = found['features']
    assert alpha['label'] == 'Alpha' and beta['label'] == 'Beta'
    assert alpha['runtime_direct_refs'] == ['app/src/main/java/com/waenhancer/xposed/features/AlphaHook.java']
    assert beta['legacy_alias'] == 'alpha'
    assert beta['alias_schema_type'] == 'BOOLEAN'
    assert beta['flags'] == ['NOT_IN_SCHEMA', 'NO_DIRECT_XPOSED_LITERAL']
    schema = java_root / 'config/PreferenceSchema.java'
    schema.write_text(schema.read_text() + '\nadd(entries, "alpha", Type.BOOLEAN, Sensitivity.PUBLIC_SETTING, Store.PUBLIC);\n')
    try:
        inventory(root)
        raise AssertionError('duplicate schema entry was not rejected')
    except ValueError as e:
        assert 'duplicate preference definitions' in str(e)
print(f"PASS: feature inventory of {report['catalog_count']} catalog entries plus synthetic fixtures")
