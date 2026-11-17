#!/usr/bin/env python3
"""Guard the actual System Health toggle callbacks against speculative UI state.

This source-level check complements the compiled WaexPreferenceManager preference
bridge tests; it does not stand in for Compose rendering or device persistence.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "app/src/main/java/com/waenhancer/ui/screens/settings/SystemHealthScreen.kt"
SCHEMA = ROOT / "app/src/main/java/com/waenhancer/config/PreferenceSchema.java"
MANAGER = ROOT / "app/src/main/java/com/waenhancer/core/preferences/WaexPreferenceManager.java"
TOGGLES = {
    "show_hook_toast": "showHookToast",
    "show_restart_sheet": "showRestartSheet",
}


def check_contract(screen: str, schema: str, manager: str) -> int:
    assert "public boolean putBooleans(Map<String, Boolean> values)" in manager
    assert "if (!editor.commit()) return false;" in manager
    checks = 0
    for key, state in TOGGLES.items():
        assert re.search(
            rf'add\(entries, "{key}", Type.BOOLEAN, Sensitivity.PUBLIC_SETTING, Store.PUBLIC\);',
            schema,
        ), f"{key}: public Boolean schema must match the batch writer"
        start = re.search(
            rf'StitchSwitch\s*\(\s*checked\s*=\s*{state}\s*,\s*'
            rf'onCheckedChange\s*=\s*\{{\s*checked\s*->',
            screen,
        )
        assert start is not None, f"{key}: no direct toggle callback"
        remainder = screen[start.end():]
        end = remainder.find("\n                            }")
        assert end > 0, f"{key}: callback delimiter missing"
        callback = remainder[:end]
        commit = f'val committed = preferences.putBooleans(mapOf("{key}" to checked))'
        readback = f'{state} = preferences.getBoolean("{key}", true)'
        feedback = "settingsSaveFailed = !committed"
        assert callback.count(commit) == 1, f"{key}: no verified Boolean commit"
        assert callback.count(readback) == 1, f"{key}: no post-write readback"
        assert callback.count(feedback) == 1, f"{key}: failure not propagated"
        assert callback.index(commit) < callback.index(readback) < callback.index(feedback)
        assert not re.search(rf'\b{state}\s*=\s*checked\b', callback), f"{key}: optimistic assignment"
        assert 'preferences.putBoolean(' not in callback, f"{key}: void writer hides failures"
        checks += 7
    assert re.search(
        r'if\s*\(settingsSaveFailed\)\s*\{\s*Text\(\s*'
        r'stringResource\(R\.string\.diag_capture_pref_failed\).*?color\s*=\s*colors\.error',
        screen,
        re.DOTALL,
    ), "Failed writes must display an accessible error near the controls"
    assert '<string name="diag_capture_pref_failed">' in (
        ROOT / 'app/src/main/res/values/diagnostic_capture_strings.xml'
    ).read_text(encoding='utf-8')
    return checks + 2


def main() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")
    manager = MANAGER.read_text(encoding="utf-8")
    checks = check_contract(screen, schema, manager)
    bad_edits = {
        "void writer": ('preferences.putBooleans(mapOf("show_hook_toast" to checked))',
                        'preferences.putBoolean("show_hook_toast", checked)'),
        "wrong target": ('mapOf("show_restart_sheet" to checked)',
                          'mapOf("show_hook_toast" to checked)'),
        "speculative state": ('showHookToast = preferences.getBoolean("show_hook_toast", true)',
                              'showHookToast = checked'),
        "ignored commit": ('showHookToast = preferences.getBoolean("show_hook_toast", true)\n'
                           '                                settingsSaveFailed = !committed',
                           'showHookToast = preferences.getBoolean("show_hook_toast", true)\n'
                           '                                settingsSaveFailed = false'),
        "wrong default": ('showRestartSheet = preferences.getBoolean("show_restart_sheet", true)',
                          'showRestartSheet = preferences.getBoolean("show_restart_sheet", false)'),
        "missing error": ('if (settingsSaveFailed) {',
                          'if (false) {'),
    }
    detected = 0
    for name, (before, after) in bad_edits.items():
        assert screen.count(before) == 1, f"Mutation anchor changed: {name}"
        try:
            check_contract(screen.replace(before, after, 1), schema, manager)
        except AssertionError:
            detected += 1
        else:
            raise AssertionError(f"Mutation incorrectly accepted: {name}")
    print(f"PASS: System Health UI {checks} contract checks; {detected}/{len(bad_edits)} negative mutations detected")
    print("LIMIT: source wiring only; Android UI and persistent-store failures are NOT_VERIFIED")


if __name__ == '__main__':
    main()
