"""Select one Robolectric runtime API without changing compilation or test bodies."""
import os
import re

CONFIG = re.compile(r"@Config\s*\((?P<body>[^)]*)\)", re.DOTALL)
SDK = re.compile(r"\bsdk\s*=\s*(?P<open>[\[{])(?P<values>[\d,\s]+)(?P<close>[\]}])")

def select_sdk(fixture_text: str, sdk: int | None,
               default_sdks: tuple[int, ...]) -> str:
    """Fail on fixture drift; None preserves every character, including EOL."""
    configs = list(CONFIG.finditer(fixture_text))
    if len(configs) != 1:
        raise ValueError("Expected exactly one class-level @Config annotation")
    config = configs[0]
    matches = list(SDK.finditer(config.group("body")))
    if len(matches) != 1:
        raise ValueError("Expected exactly one explicit @Config SDK list")
    match = matches[0]
    if (match.group("open"), match.group("close")) not in [("[", "]"), ("{", "}")]:
        raise ValueError("Mismatched @Config SDK delimiters")
    values = tuple(int(value.strip()) for value in match.group("values").split(","))
    if values != tuple(default_sdks):
        raise ValueError(f"Fixture SDK contract changed: {values} != {default_sdks}")
    if sdk is None:
        return fixture_text
    if type(sdk) is not int or sdk not in range(24, 38):
        raise ValueError("Single runtime API must be an integer from 24 through 37")
    start = config.start("body") + match.start("values")
    end = config.start("body") + match.end("values")
    return fixture_text[:start] + str(sdk) + fixture_text[end:]


def runtime_env(sdk: int | None) -> dict[str, str] | None:
    """Keep defaults untouched; newer Android shared memory needs this JVM export."""
    if sdk is None or sdk < 35:
        return None
    env = os.environ.copy()
    flag = "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED"
    options = env.get("JAVA_TOOL_OPTIONS", "")
    if flag not in options.split():
        env["JAVA_TOOL_OPTIONS"] = (options + " " + flag).strip()
    return env
