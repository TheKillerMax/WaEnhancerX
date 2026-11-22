#!/usr/bin/env python3
"""Check exact Robolectric repository configuration, scope and fail-closed inputs."""
import os
from pathlib import Path
from unittest.mock import patch

from robolectric_runtime_repo import ENV_KEY, MAVEN_CENTRAL, GOOGLE_PUBLIC_MIRROR, repository_url

ROOT = Path(__file__).resolve().parents[1]

with patch.dict(os.environ, {}, clear=True):
    assert repository_url() == MAVEN_CENTRAL
with patch.dict(os.environ, {ENV_KEY: GOOGLE_PUBLIC_MIRROR}):
    assert repository_url() == GOOGLE_PUBLIC_MIRROR
with patch.dict(os.environ, {ENV_KEY: MAVEN_CENTRAL}):
    assert repository_url() == MAVEN_CENTRAL
for bad in ("https://unreviewed.invalid/maven2", "http://repo.maven.apache.org/maven2",
            "", "https://maven-central.storage-download.googleapis.com/maven2?token=secret"):
    with patch.dict(os.environ, {ENV_KEY: bad}):
        try:
            repository_url()
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unreviewed runtime repository accepted: {bad!r}")

direct = (
    "android_home_restart_test.py", "android_presence_row_test.py",
    "android_preserved_dispatch_test.py", "android_preserved_store_test.py",
    "android_work_profile_test.py",
)
generated = (
    "verify_stability_framework.py", "verify_runtime_framework.py",
    "verify_interface_scale_framework.py",
)
for name in direct:
    source = (ROOT / "qa" / name).read_text(encoding="utf-8")
    assert "from robolectric_runtime_repo import repository_url" in source
    assert "'-Drobolectric.dependency.repo.url=' + repository_url()" in source
    assert "'-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2'" not in source
for name in generated:
    source = (ROOT / "qa" / name).read_text(encoding="utf-8")
    assert "from robolectric_runtime_repo import repository_url" in source
    assert 'it.systemProperty("robolectric.dependency.repo.url", ' in source
    assert "repository_url()" in source
ci = (ROOT / ".github/workflows/source-qa.yml").read_text(encoding="utf-8")
assert "WAEX_ROBOLECTRIC_RUNTIME_REPO: " + GOOGLE_PUBLIC_MIRROR in ci
assert "robolectric.offline=true" not in ci, "Do not bypass runtime dependency checks"
print(f"PASS: default and 2 allowed sources, 4 denied sources, {len(direct)} JVM and "
      f"{len(generated)} Gradle CI probes, exact protected workflow binding")
