"""Pinned public runtime-APK dependency repository policy for isolated Robolectric QA.

Default remains Maven Central. The alternate is a read-only public GCS mirror
documented by Google Cloud, never an arbitrary host from CI/user input.
Neither selection relaxes test assertions nor changes Robolectric artifacts.
"""
import os

MAVEN_CENTRAL = "https://repo.maven.apache.org/maven2"
GOOGLE_PUBLIC_MIRROR = "https://maven-central.storage-download.googleapis.com/maven2/"
ENV_KEY = "WAEX_ROBOLECTRIC_RUNTIME_REPO"


def repository_url():
    source = os.environ.get(ENV_KEY, MAVEN_CENTRAL)
    if source not in (MAVEN_CENTRAL, GOOGLE_PUBLIC_MIRROR):
        raise ValueError(f"Disallowed Robolectric runtime Maven repository: {source!r}")
    return source
