#!/usr/bin/env python3
"""Static compatibility assertions; Android instrumentation is still required."""
from pathlib import Path
r = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/waenhancer'
theme = (r/'ui/designsystem/WaexTheme.kt').read_text()
main = (r/'app/MainActivity.kt').read_text()
permission = (r/'app/PermissionsActivity.kt').read_text()
theme_menu = (r/'ui/screens/settings/ModuleSettingsScreen.kt').read_text()
checks = {
    'legacy palette fallback': '?: if (darkTheme) darkColors else lightColors' in theme,
    'Android 12+ guard': 'useMonet && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S' in theme,
    'dynamic dark colors': 'dynamicDarkColorScheme(context)' in theme,
    'dynamic light colors': 'dynamicLightColorScheme(context)' in theme,
    'M3 role mapping': 'monetWaexColors(scheme: ColorScheme' in theme,
    'main opt-in': 'useMonet = themeMode == "Monet"' in main,
    'onboarding opt-in': 'useMonet = themeMode == "Monet"' in permission,
    'only show supported menu': 'if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) listOf("Monet") else emptyList()' in theme_menu,
}
for key, value in checks.items():
    assert value, f'Monet wiring regression: {key}'
print('PASS: 8 Monet compatibility/wiring assertions (static, not UI runtime)')
