"""Batch directory cleanup runs after connection unwind, including setup errors."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import depwitness
from depwitness import AuditError, audit_many
from depwitness.disk import TemporaryDirectory


class BatchCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self.path = self.root / "data.csv"
        self.path.write_text("a,b\nx,1\nx,2\ny,3\n", encoding="utf-8")
        self.rules = [{"determinant": ["a"], "dependent": ["b"]}] * 3

    def batch(self):
        return audit_many(self.path, rules=self.rules, storage="sqlite", temp_dir=self.storage)

    def assert_clean(self):
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_connections_all_close_before_any_cleanup_on_success(self):
        self.check_cleanup_order()

    def test_connections_all_close_before_any_cleanup_on_setup_failure(self):
        self.check_cleanup_order(fail_setup=True)

    def check_cleanup_order(self, fail_setup=False):
        connect, cleanup = sqlite3.connect, TemporaryDirectory.cleanup
        active, cleanups = [], []

        class Connection:
            def __init__(self, *args, **kwargs):
                self.real = connect(*args, **kwargs)
                active.append(self)

            def execute(self, *args, **kwargs):
                if fail_setup and len(active) == 3:
                    raise sqlite3.OperationalError("injected third setup failure")
                return self.real.execute(*args, **kwargs)

            def close(self):
                self.real.close()
                active.remove(self)

        def checked_cleanup(temporary):
            self.assertEqual(active, [], "directory cleanup precedes batch connection unwind")
            cleanup(temporary)
            cleanups.append(temporary.name)

        with (
            patch("depwitness.disk.sqlite3.connect", Connection),
            patch.object(TemporaryDirectory, "cleanup", checked_cleanup),
        ):
            if fail_setup:
                with self.assertRaisesRegex(AuditError, "third setup failure"):
                    self.batch()
            else:
                result = self.batch()
                self.assertEqual(len(result["rules"]), 3)
                self.assertFalse(result["passed"])
        self.assertEqual(len(cleanups), 3)
        self.assert_clean()

    def test_close_failure_still_unwinds_every_connection_and_directory(self):
        connect = sqlite3.connect
        closed = []

        class Connection:
            def __init__(self, *args, **kwargs):
                self.real = connect(*args, **kwargs)

            def execute(self, *args, **kwargs):
                return self.real.execute(*args, **kwargs)

            def close(self):
                self.real.close()
                closed.append(self)
                if len(closed) == 1:
                    raise sqlite3.OperationalError("injected batch close failure")

        with (
            patch("depwitness.disk.sqlite3.connect", Connection),
            self.assertRaisesRegex(AuditError, "batch close failure"),
        ):
            self.batch()
        self.assertEqual(len(closed), 3)
        self.assert_clean()

    def test_cleanup_failure_still_attempts_every_directory_and_rejects_report(self):
        cleanup = TemporaryDirectory.cleanup
        cleaned = []

        def fail_once(temporary):
            cleanup(temporary)
            cleaned.append(temporary.name)
            if len(cleaned) == 1:
                raise OSError("injected batch cleanup failure")

        with (
            patch.object(TemporaryDirectory, "cleanup", fail_once),
            self.assertRaisesRegex(AuditError, "batch cleanup failure"),
        ):
            self.batch()
        self.assertEqual(len(cleaned), 3)
        self.assert_clean()

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor exhaustion regression")
    def test_real_descriptor_exhaustion_cleans_setup_failure_api_and_cli(self):
        # Run alone so the test runner's descriptors and limits are untouched.
        script = r"""
import contextlib, io, json, resource, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from depwitness import AuditError, audit_many
from depwitness.__main__ import main
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
if hard != resource.RLIM_INFINITY and hard < 64:
    print(json.dumps({"skip": "hard descriptor limit below regression limit"}))
    raise SystemExit
resource.setrlimit(resource.RLIMIT_NOFILE, (64, hard))
path, storage = Path(sys.argv[2]), Path(sys.argv[3])
rule = {"determinant": ["a"], "dependent": ["b"]}
try:
    audit_many(path, rules=[rule] * 100, storage="sqlite", temp_dir=storage)
except AuditError:
    pass
else:
    raise AssertionError("descriptor exhaustion did not occur")
assert list(storage.iterdir()) == [], "API left temporary storage after handled exhaustion"
out, err = io.StringIO(), io.StringIO()
args = [str(path), "--storage", "sqlite", "--temp-dir", str(storage)]
for _ in range(100):
    args.extend(["--rule", json.dumps(rule)])
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(args)
assert code == 2 and out.getvalue() == "" and err.getvalue()
assert list(storage.iterdir()) == [], "CLI left temporary storage after handled exhaustion"
print(json.dumps({"api_failed_closed": True, "cli_exit": code, "remaining_indexes": 0}))
"""
        source = str(Path(depwitness.__file__).resolve().parent.parent)
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, source, str(self.path), str(self.storage)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        if "skip" in report:
            self.skipTest(report["skip"])
        self.assertEqual(report, {"api_failed_closed": True, "cli_exit": 2, "remaining_indexes": 0})
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
