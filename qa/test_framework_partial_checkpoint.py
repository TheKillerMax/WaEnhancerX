#!/usr/bin/env python3
"""Synthetic partial graph and cooldown controls. No external network."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import framework_partial_checkpoint as partial
from framework_dependency_bundle import LOCK, sha


class PartialChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="waex-partial-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = self.root / "lock.json"
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        self.items = []
        self.bodies = {}
        for item in lock["files"]:
            body = ("synthetic fixture " + item["name"]).encode()
            item.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            self.bodies[item["name"]] = body
            if item["directory"] == "deps":
                self.items.append(item)
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        self.deps = self.root / "producer"
        self.deps.mkdir()
        self.checkpoint = self.root / "partial"
        self.receipt = self.root / "receipt.json"
        rows = []
        for i, item in enumerate(self.items):
            attempts = []
            if i < 23:
                (self.deps / item["name"]).write_bytes(self.bodies[item["name"]])
                attempts = [{"status": "verified", "http_status": 200}]
            elif i == 23:
                attempts = [{"status": "retry_deferred_beyond_budget", "http_status": 429,
                             "retry_after_seconds": 63865}]
            rows.append({"name": item["name"], "bytes": item["bytes"],
                         "sha256": item["sha256"], "attempts": attempts})
        self.record = {"accepted": False, "worker_closed": True, "lock_sha256": sha(self.lock),
                       "files": rows}
        self.write_receipt()

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.record), encoding="utf-8")

    def capture(self):
        return partial.capture(self.deps, self.receipt, self.checkpoint, self.lock, now=1000)

    def verify(self, now=64865):
        return partial.verify(self.checkpoint, self.lock, now=now)

    def test_exact_partial_and_cooldown_boundary(self):
        m = self.capture()
        self.assertEqual(23, len(m["files"]))
        self.assertFalse(m["complete"])
        self.assertEqual(64865, m["resume_not_before_epoch"])
        with self.assertRaisesRegex(ValueError, "Retry-After is still active"):
            self.verify(now=64864.999)
        self.assertEqual(23, self.verify()["verified_files"])
        self.assertEqual(23, self.verify(now=65000)["verified_files"])
        for item in self.items[:23]:
            self.assertEqual(self.bodies[item["name"]],
                             (self.checkpoint/"deps"/item["name"]).read_bytes())

    def test_no_external_requests(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            self.capture()
            self.verify()

    def test_non_deferred_failure_is_not_cached(self):
        self.record["files"][23]["attempts"][0]["status"] = "nonretryable_failure"
        self.write_receipt()
        self.assertIsNone(self.capture())
        self.assertFalse(self.checkpoint.exists())

    def test_worker_must_be_closed(self):
        self.record["worker_closed"] = False
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "failed, closed"):
            self.capture()

    def test_success_cannot_be_relabelled_partial(self):
        self.record["accepted"] = True
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "failed, closed"):
            self.capture()

    def test_receipt_lock_and_entry_identity(self):
        for mutation in ("lock", "entry"):
            with self.subTest(mutation=mutation):
                old = self.record["lock_sha256"]
                if mutation == "lock":
                    self.record["lock_sha256"] = "0"*64
                else:
                    self.record["files"][0]["sha256"] = "0"*64
                self.write_receipt()
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    self.capture()
                self.record["lock_sha256"] = old

    def test_invalid_or_ambiguous_deferral_is_rejected(self):
        attempt = self.record["files"][23]["attempts"][0]
        for delay in (None, -1, 0, float("inf"), "63865", True):
            with self.subTest(delay=delay):
                attempt["retry_after_seconds"] = delay
                self.write_receipt()
                with self.assertRaisesRegex(ValueError, "valid server interval"):
                    self.capture()
        attempt["retry_after_seconds"] = 63865
        self.record["files"][24]["attempts"] = [dict(attempt)]
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.capture()

    def test_unknown_or_corrupt_producer_file_is_rejected(self):
        rogue = self.deps/"unreviewed.jar"
        rogue.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.capture()
        rogue.unlink()
        (self.deps/self.items[0]["name"]).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.capture()
        self.assertFalse(self.checkpoint.exists())

    def test_corrupt_restored_bytes_are_not_accepted(self):
        self.capture()
        (self.checkpoint/"deps"/self.items[0]["name"]).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.verify()

    def test_manifest_cannot_omit_an_existing_file(self):
        self.capture()
        path = self.checkpoint/partial.MANIFEST
        m = json.loads(path.read_text())
        del m["files"][self.items[0]["name"]]
        path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            self.verify()

    def test_manifest_cannot_shorten_interval_by_deadline_only(self):
        self.capture()
        path = self.checkpoint/partial.MANIFEST
        m = json.loads(path.read_text())
        m["resume_not_before_epoch"] = 1000
        path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "Invalid partial checkpoint clock"):
            self.verify()

    def test_existing_checkpoint_and_overlapping_paths_rejected(self):
        self.capture()
        with self.assertRaisesRegex(ValueError, "fresh checkpoint"):
            self.capture()
        with self.assertRaisesRegex(ValueError, "must be separate"):
            partial.capture(self.deps, self.receipt, self.deps/"nested", self.lock)

    def test_zero_cached_bytes_still_retain_cooldown(self):
        for p in self.deps.iterdir():
            p.unlink()
        m = self.capture()
        self.assertEqual({}, m["files"])
        # Cache transport may omit empty directories.
        (self.checkpoint/"deps").rmdir()
        with self.assertRaisesRegex(ValueError, "Retry-After is still active"):
            self.verify(now=1001)
        self.assertEqual(0, self.verify()["verified_files"])

    def test_checkpoint_is_not_complete_bundle(self):
        for item in self.items[23:]:
            (self.deps/item["name"]).write_bytes(self.bodies[item["name"]])
        with self.assertRaisesRegex(ValueError, "remain incomplete"):
            self.capture()

    def test_missing_or_extra_restored_paths_rejected(self):
        self.capture()
        (self.checkpoint/"unreviewed.txt").write_text("bad")
        with self.assertRaisesRegex(ValueError, "Unexpected partial checkpoint paths"):
            self.verify()
        (self.checkpoint/"unreviewed.txt").unlink()
        (self.checkpoint/"deps"/self.items[0]["name"]).unlink()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
