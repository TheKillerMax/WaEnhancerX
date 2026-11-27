"""Synthetic exact-byte cache seed controls; no network or real API claim."""
import tempfile
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import seed_core_gradle_cache as subject

class SeedChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "gradle"
        self.cache = self.root / "dedicated"
        self.body = b"synthetic reviewed API"
        self.item = {"name": "core-1.18.0.aar", "bytes": len(self.body),
                     "sha256": hashlib.sha256(self.body).hexdigest()}
        self.module = self.home / "caches/modules-2/files-2.1/androidx.core/core/1.18.0/hash"
        self.source = self.module / self.item["name"]
        self.dest = self.cache / self.item["name"]
        mock = patch.dict(subject.CONFIGS, {"core": {"source": self.item}})
        mock.start()
        self.addCleanup(mock.stop)

    def source_bytes(self, body):
        self.module.mkdir(parents=True, exist_ok=True)
        self.source.write_bytes(body)

    def test_missing_is_not_prepared(self):
        self.assertEqual("not_available", subject.seed(self.home, self.cache))
        self.assertFalse(self.dest.exists())

    def test_verified_seed_and_idempotence(self):
        self.source_bytes(self.body)
        self.assertEqual("verified_gradle_seed", subject.seed(self.home, self.cache))
        self.assertEqual(self.body, self.dest.read_bytes())
        self.assertEqual("already_verified", subject.seed(self.home, self.cache))
        self.assertEqual([self.dest], list(self.cache.iterdir()))

    def test_corrupt_source_is_not_published(self):
        self.source_bytes(b"x" * len(self.body))
        with self.assertRaises(ValueError):
            subject.seed(self.home, self.cache)
        self.assertFalse(self.dest.exists())

    def test_bad_existing_cache_is_not_overwritten(self):
        self.source_bytes(self.body)
        self.cache.mkdir()
        self.dest.write_bytes(b"bad")
        with self.assertRaises(ValueError):
            subject.seed(self.home, self.cache)
        self.assertEqual(b"bad", self.dest.read_bytes())

    def test_multiple_sources_must_all_match(self):
        self.source_bytes(self.body)
        second = self.module.parent / "bad" / self.item["name"]
        second.parent.mkdir()
        second.write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            subject.seed(self.home, self.cache)
        self.assertFalse(self.dest.exists())

if __name__ == "__main__":
    unittest.main()
