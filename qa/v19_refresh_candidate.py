#!/usr/bin/env python3
"""Reconcile reviewed QA only; caller pins and verifies the full candidate tree."""
from pathlib import Path
import subprocess

root = Path.cwd()
previous = '5e3d0e9de2231e5986e6a639de1cd8df64e686e9'
paths = ['.github/workflows/source-qa.yml', 'qa/README.md', 'qa/catalog_source.py',
         'qa/feature_contract_inventory.py', 'qa/test_archived_chats_entry.py',
         'qa/test_catalog_schema_alias_contract.py', 'qa/test_catalog_source.py',
         'qa/test_proximity_ui_wiring.py', 'qa/test_style_non_boolean_guard.py']
for name in paths:
    (root / name).write_bytes(subprocess.check_output(['git', 'show', previous + ':' + name]))

p = root / 'qa/test_feature_contract_inventory.py'
s = p.read_text()
old = "        'config/FeatureCatalog.kt': 'private val canonicalGroupOverrides = mapOf()',"
new = '''        'config/FeatureCatalog.kt': '\'\'private const val ASSET_NAME = "preference_catalog.json"
private val canonicalGroupOverrides = mapOf(
)
.flatMap { it.items() }
.filter { item -> canonicalGroupOverrides[item.key]?.let { it == item.groupId } ?: true }
.distinctBy { it.key }
'\'\','''
assert old in s
s = s.replace(old, new)
old = "asset.write_text('[{\"id\":\"test\",\"keys\":[\"alpha\",\"beta\"]}]')"
new = '''asset.write_text('[{"id":"test","tabIndex":1,"tabId":"privacy","keys":["alpha","beta"]}]')
    resources = root/'app/src/main/res/values/strings.xml'
    resources.parent.mkdir(parents=True, exist_ok=True)
    resources.write_text('\'\'<resources>
      <string name="sec_test">Test group</string>
      <string name="catalog_tab_privacy">Privacy</string>
      <string name="feat_alpha_title">Alpha</string>
      <string name="feat_alpha_desc">Alpha description</string>
      <string name="feat_beta_title">Beta</string>
      <string name="feat_beta_desc">Beta description</string>
    </resources>'\'\')'''
assert old in s
s = s.replace(old, new)
s = s.replace("alpha, beta = found['features']", "alpha, beta = found['features']\n    assert alpha['label'] == 'Alpha' and beta['label'] == 'Beta'")
p.write_text(s)
p = root / 'qa/README.md'
s = p.read_text()
s += '\nThe localized reader extends the upstream JSON migration; its synthetic fixture\nretains schema/alias assertions and supplies the same routing/resources as production.\n'
p.write_text(s)

p = root / 'qa/test_private_hook_logs.py'
s = p.read_text()
old = '    calls = list(hook_logs(src))\n    assert len(calls) == expected, ('
new = '''    calls = list(hook_logs(src))
    # Upstream 93cc35d adds one reviewed, literal-only recipient failure diagnostic.
    # Keep exact counts and scan every expression; do not allow arbitrary extra logs.
    recipient_failure = 'TAG + " Cannot dispatch: outgoing recipient is unavailable"'
    if rel.endswith('/BlueOnReplyHook.java') and recipient_failure in calls:
        expected += 1
    assert len(calls) == expected, ('''
assert old in s
s = s.replace(old, new)
old = "assert 'getOrFindJobManager()' in blue"
new = '''if 'Cannot dispatch: outgoing recipient is unavailable' in blue:
    dispatch = blue.split('private static int sendPendingReadJobs(String jid)', 1)[1].split('private String extractRemoteJid(', 1)[0]
    assert 'if (key == null)' in dispatch and 'return 0;' in dispatch
    assert 'PENDING_JOBS.remove(key)' in dispatch or 'PENDING_JOBS.drain(key)' in dispatch
    for unsafe_fallback in ('getUserPart(', 'lastHiddenConversationJid', 'PENDING_JOBS.size() == 1'):
        assert unsafe_fallback not in dispatch, 'Recipient fallback restored: ' + unsafe_fallback
assert 'getOrFindJobManager()' in blue'''
assert old in s
s = s.replace(old, new)
s = s.replace('    \'TAG + " stored " + jid\',', '    \'TAG + " stored " + jid\',\n    \'TAG + " Cannot dispatch: outgoing recipient is unavailable " + jid\',')
p.write_text(s)
