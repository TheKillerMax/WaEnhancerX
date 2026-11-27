#!/usr/bin/env python3
"""Seed only the reviewed OkHttp API from a restored public Gradle cache."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
from framework_dependency_bundle import checked
from prepare_public_apis import CONFIGS

def seed(gradle_home, cache):
    item = CONFIGS["okhttp"]["source"]
    cache = Path(cache)
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        raise ValueError("Expected a dedicated real OkHttp cache directory")
    dest = cache / item["name"]
    if dest.exists() or dest.is_symlink():
        checked(dest, item)
        return "already_verified"
    root = Path(gradle_home) / "caches/modules-2/files-2.1/com.squareup.okhttp3/okhttp/4.12.0"
    if root.is_symlink():
        raise ValueError("Unexpected symbolic Gradle module directory")
    choices = sorted(root.glob("*/" + item["name"]))
    if not choices:
        return "not_available"
    for source in choices:
        if source.parent.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unexpected Gradle cache entry path")
        checked(source, item)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache, prefix=".seed-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(choices[0], temporary)
        checked(temporary, item)
        os.link(temporary, dest)
        checked(dest, item)
    finally:
        temporary.unlink(missing_ok=True)
    return "verified_gradle_seed"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gradle-home", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps({"status": seed(a.gradle_home, a.cache), "artifact": "okhttp-4.12.0"}))

if __name__ == "__main__":
    main()
