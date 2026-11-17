#!/usr/bin/env python3
"""Prevent informational/debug logging from returning to production sources."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = [ROOT / "app/src/main", ROOT / "licensing/src/main", ROOT / "samples"]
SOURCE_SUFFIXES = {".java", ".kt", ".kts", ".js", ".ts", ".tsx", ".jsx"}

forbidden = {
    "verbose Android log": re.compile(r"\b(?:android\.util\.)?Log\.v\s*\("),
    "debug Android log": re.compile(r"\b(?:android\.util\.)?Log\.d\s*\("),
    "informational Android log": re.compile(r"\b(?:android\.util\.)?Log\.i\s*\("),
    "standard output": re.compile(r"\bSystem\.out\.print(?:ln)?\s*\("),
    "console informational log": re.compile(r"\bconsole\.(?:log|info|debug)\s*\("),
    "hooking-mode diagnostic": re.compile(r"\[HookingMode]"),
    "lazy lifecycle diagnostic": re.compile(r"\[LazyHooks]"),
    "successful cache diagnostic": re.compile(r"\[DexCache].*\b(?:resolved|invalidated)\b", re.I),
}

violations: list[str] = []
files_checked = 0
for source_root in SOURCE_ROOTS:
    if not source_root.exists():
        continue
    for source in source_root.rglob("*"):
        if source.suffix not in SOURCE_SUFFIXES or "build" in source.parts:
            continue
        files_checked += 1
        text = source.read_text(encoding="utf-8")
        for label, pattern in forbidden.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{source.relative_to(ROOT)}:{line}: {label}")

# The embedded APKMirror WebViews may encounter signed download URLs, cookies
# and page-derived text. Keep only the three reviewed, metadata-only warnings;
# dynamic URL/content logging must require another explicit privacy review.
apk_mirror = (ROOT / "app/src/main/java/com/waenhancer/ui/screens/settings/ApkMirrorVersionsScreen.kt").read_text(encoding="utf-8")
get_version = (ROOT / "app/src/main/java/com/waenhancer/ui/screens/settings/GetVersionScreen.kt").read_text(encoding="utf-8")
reviewed_warnings = [
    'Log.w(TAG, "renderer gone (crashed=${detail.didCrash()})")',
    'Log.w(TAG, "main frame error code=${error.errorCode}")',
    'Log.w(TAG, "feed load gave up (loadFailed=$loadFailed, responded=$pageResponded)")',
]


def warning_expressions(source):
    return [line.strip() for line in source.splitlines() if "Log.w(" in line or "Log.e(" in line]


assert warning_expressions(apk_mirror) == reviewed_warnings, (
    "APKMirror warning payloads or callsites changed; re-review WebView log privacy"
)
assert not re.search(r"\bLog\.[a-z]+\s*\(", get_version), (
    "GetVersion WebView must not log redirect, download or JavaScript payloads"
)
for unsafe_change in (
    apk_mirror.replace("error code=${error.errorCode}", "error for ${request.url}"),
    apk_mirror + '\nLog.w(TAG, "unexpected download URL: $url")\n',
    apk_mirror.replace(reviewed_warnings[2], ""),
):
    assert warning_expressions(unsafe_change) != reviewed_warnings, (
        "WebView privacy negative control accepted a changed warning"
    )

if violations:
    raise SystemExit("Production logging policy violations:\n- " + "\n- ".join(violations))

print(f"PASS: {files_checked} production source files contain no informational/debug logs; "
      "APKMirror WebView warning payloads reviewed with 3 negative controls")
