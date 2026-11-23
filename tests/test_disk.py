import csv
import io
import os
import random
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, Limits, audit
from depwitness.__main__ import main
from depwitness.disk import _DiskGroups, sqlite_groups


class DiskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "input.csv"
        self.storage = self.root / "storage"
        self.storage.mkdir()

    def rows(self, rows, header=("k", "v"), bom=False):
        with self.path.open("w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
            csv.writer(f).writerows([header, *rows])

    def run_disk(self, **kwargs):
        return audit(
            self.path,
            determinant=["k"],
            dependent=["v"],
            storage="sqlite",
            temp_dir=self.storage,
            **kwargs,
        )

    def assert_clean(self):
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_complete_report_parity(self):
        rows = [("a", "x"), ("b", "p"), ("a", "y"), ("b", "q"), ("a", "x"), ("a", "z")]
        self.rows(rows)
        for n in (0, 1, 2, 1000):
            self.assertEqual(
                self.run_disk(examples=n),
                audit(self.path, determinant=["k"], dependent=["v"], examples=n),
            )
            self.assert_clean()

    def test_generated_report_parity(self):
        randomizer = random.Random(619204)
        values = ["", "NA", "NULL", "a", "a,b", "a\nb", "é", "e\u0301", "001", "1", "\\", '"']
        for case in range(100):
            rows = [
                tuple(randomizer.choice(values) for _ in range(4))
                for _ in range(randomizer.randrange(60))
            ]
            self.rows(rows, ("k", "k2", "v", "ignored"), bom=case % 2 == 0)
            for cap in (0, 1, 7):
                kwargs = {"determinant": ["k", "k2"], "dependent": ["v"], "examples": cap}
                self.assertEqual(
                    audit(self.path, **kwargs),
                    audit(self.path, storage="sqlite", temp_dir=self.storage, **kwargs),
                )
                self.assert_clean()

    def test_large_conflicting_group(self):
        self.rows([("a", str(i)) for i in range(2000)] + [("a", "0")] * 10)
        report = self.run_disk(examples=1)
        self.assertEqual(report, audit(self.path, determinant=["k"], dependent=["v"], examples=1))
        self.assertEqual(report["counts"]["minimum_record_removals"], 1999)
        self.assert_clean()

    def test_counts_larger_than_sqlite_integers(self):
        n = 2**100
        with sqlite_groups(self.storage) as groups:
            groups[("key",)] = [n, ("v",), Counter({("v",): n - 3, ("w",): 3}), 1]
            group = groups[("key",)]
            self.assertEqual(group[0], n)
            self.assertEqual(group[2][("v",)], n - 3)
            self.assertEqual(group[2][("missing",)], 0)
            group[2][("v",)] += 1
            group[0] += 1
            groups[("key",)] = group
            restored = next(groups.values())
            self.assertEqual(restored[0], n + 1)
            self.assertEqual(max(restored[2].values()), n - 2)
        self.assert_clean()

    def test_invalid_storage_and_memory_temp_dir(self):
        self.rows([("k", "v")])
        for storage in ("bad", None, [], 1):
            with self.assertRaises(AuditError):
                audit(self.path, determinant=["k"], dependent=["v"], storage=storage)
        with self.assertRaises(AuditError):
            audit(self.path, determinant=["k"], dependent=["v"], temp_dir=self.storage)
        self.assert_clean()

    def test_group_limit(self):
        self.rows([("a", "x"), ("b", "x")])
        with self.assertRaisesRegex(AuditError, "group limit"):
            self.run_disk(limits=Limits(max_groups=1))
        self.assert_clean()

    def test_byte_record_and_field_limits(self):
        self.rows([("a", "x"), ("a", "y")])
        for limits in (Limits(max_bytes=8), Limits(max_records=1), Limits(max_field_chars=1)):
            if limits.max_field_chars == 1:
                self.rows([("aa", "x")])
            with self.assertRaises(AuditError):
                self.run_disk(limits=limits)
            self.assert_clean()

    def test_late_invalid_input_never_returns_partial_report(self):
        for ending in (b"broken\n", b"a,\x00\n", b"a,\xff\n", b'a,"unfinished'):
            self.path.write_bytes(b"k,v\na,x\na,y\n" + ending)
            with self.assertRaises(AuditError):
                self.run_disk(examples=0)
            self.assert_clean()

    def test_missing_storage_parent(self):
        self.rows([("a", "x")])
        with self.assertRaisesRegex(AuditError, "temporary dependency storage"):
            audit(
                self.path,
                determinant=["k"],
                dependent=["v"],
                storage="sqlite",
                temp_dir=self.storage / "missing",
            )
        self.assert_clean()

    def test_connect_failure_cleans_directory(self):
        self.rows([("a", "x")])
        with (
            patch("depwitness.disk.sqlite3.connect", side_effect=sqlite3.OperationalError("full")),
            self.assertRaisesRegex(AuditError, "temporary dependency storage"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_write_failure_cli_has_no_partial_json(self):
        self.rows([("a", "x"), ("a", "y")])
        original = _DiskGroups.__setitem__

        def fail_after_one(groups, key, group):
            if group[0] > 1:
                raise AuditError("injected storage write failure")
            return original(groups, key, group)

        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(_DiskGroups, "__setitem__", fail_after_one),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = main(
                [
                    str(self.path),
                    "--determinant",
                    "k",
                    "--dependent",
                    "v",
                    "--storage",
                    "sqlite",
                    "--temp-dir",
                    str(self.storage),
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("storage write failure", err.getvalue())
        self.assert_clean()

    def test_private_files_and_selected_values_only(self):
        self.rows([("a", "x", "private-unselected-marker")], ("k", "v", "ignored"))
        original = _DiskGroups.__setitem__
        inspected = []

        def inspect(groups, key, group):
            result = original(groups, key, group)
            (directory,) = self.storage.iterdir()
            database = directory / "dependency.sqlite3"
            if os.name == "posix":
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
                self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            data = groups.execute("SELECT k, representative FROM groups").fetchall()
            self.assertEqual(data, [('["a"]', '["x"]')])
            inspected.append(True)
            return result

        with patch.object(_DiskGroups, "__setitem__", inspect):
            report = self.run_disk()
        self.assertTrue(inspected)
        self.assertNotIn("private-unselected-marker", str(report))
        self.assert_clean()

    def test_cleanup_failure_has_no_report(self):
        self.rows([("a", "x")])
        from depwitness.disk import TemporaryDirectory

        original = TemporaryDirectory.cleanup

        def cleanup(temporary):
            original(temporary)
            raise OSError("injected cleanup failure")

        with (
            patch.object(TemporaryDirectory, "cleanup", cleanup),
            self.assertRaisesRegex(AuditError, "cleanup failure"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_close_failure_still_cleans_directory(self):
        self.rows([("a", "x")])
        connect = sqlite3.connect

        class Connection:
            def __init__(self, *args, **kwargs):
                self.real = connect(*args, **kwargs)

            def execute(self, *args, **kwargs):
                return self.real.execute(*args, **kwargs)

            def close(self):
                self.real.close()
                raise sqlite3.OperationalError("injected close failure")

        with (
            patch("depwitness.disk.sqlite3.connect", Connection),
            self.assertRaisesRegex(AuditError, "close failure"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_fetch_failure_is_storage_error(self):
        self.rows([("a", "x")])
        original = _DiskGroups.execute

        class Cursor:
            def fetchone(self):
                raise sqlite3.OperationalError("injected fetch failure")

            def close(self):
                pass

        def execute(groups, sql, parameters=()):
            if sql.startswith("SELECT n, representative, promoted, first_record FROM groups"):
                return Cursor()
            return original(groups, sql, parameters)

        with (
            patch.object(_DiskGroups, "execute", execute),
            self.assertRaisesRegex(AuditError, "fetch failure"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_summary_iteration_failure_is_storage_error(self):
        self.rows([("a", "x"), ("a", "y")])
        original = _DiskGroups.execute

        class Cursor:
            def __iter__(self):
                raise sqlite3.OperationalError("injected iteration failure")

            def close(self):
                pass

        def execute(groups, sql, parameters=()):
            if sql == "SELECT n FROM frequencies WHERE k = ?":
                return Cursor()
            return original(groups, sql, parameters)

        with (
            patch.object(_DiskGroups, "execute", execute),
            self.assertRaisesRegex(AuditError, "iteration failure"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_group_iteration_failure_is_storage_error(self):
        self.rows([("a", "x")])
        original = _DiskGroups.execute

        class Cursor:
            def __iter__(self):
                raise sqlite3.OperationalError("injected group iteration failure")

            def close(self):
                pass

        def execute(groups, sql, parameters=()):
            if sql == "SELECT k FROM groups ORDER BY rowid":
                return Cursor()
            return original(groups, sql, parameters)

        with (
            patch.object(_DiskGroups, "execute", execute),
            self.assertRaisesRegex(AuditError, "group iteration failure"),
        ):
            self.run_disk()
        self.assert_clean()

    def test_successful_cli_json_is_backend_independent(self):
        self.rows([("a", "x"), ("a", "y")])
        outputs = []
        for storage in ("memory", "sqlite"):
            out, err = io.StringIO(), io.StringIO()
            args = [
                str(self.path),
                "--determinant",
                "k",
                "--dependent",
                "v",
                "--storage",
                storage,
                "--examples",
                "1",
            ]
            if storage == "sqlite":
                args += ["--temp-dir", str(self.storage)]
            with patch("sys.stdout", out), patch("sys.stderr", err):
                self.assertEqual(main(args), 1)
            outputs.append(out.getvalue())
            self.assertEqual(err.getvalue(), "")
        self.assertEqual(*outputs)
        self.assert_clean()

    def test_invalid_temp_dir_is_storage_error(self):
        self.rows([("a", "x")])
        with self.assertRaisesRegex(AuditError, "temporary dependency storage"):
            audit(self.path, determinant=["k"], dependent=["v"], storage="sqlite", temp_dir=[])
        self.assert_clean()

    def test_writes_close_cursors_and_wrap_close_failure(self):
        class Cursor:
            rowcount = 1

            def close(self):
                raise sqlite3.OperationalError("injected cursor close failure")

        class Connection:
            def execute(self, *args):
                return Cursor()

        groups = _DiskGroups(Connection())
        with self.assertRaisesRegex(AuditError, "cursor close failure"):
            groups.write("SELECT 1")

    def test_cleanup_is_explicit_before_return(self):
        self.rows([("a", "x")])
        from depwitness.disk import TemporaryDirectory

        original = TemporaryDirectory.cleanup
        cleaned = []

        def cleanup(temporary):
            original(temporary)
            cleaned.append(temporary.name)

        with patch.object(TemporaryDirectory, "cleanup", cleanup):
            self.run_disk()
            self.assertEqual(len(cleaned), 1)
        self.assert_clean()

    def test_unavailable_sqlite_fails_only_optional_backend(self):
        import builtins

        self.rows([("a", "x")])
        original = builtins.__import__

        def unavailable(name, *args, **kwargs):
            if name == "disk":
                raise ImportError("injected unavailable sqlite module")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", unavailable):
            self.assertTrue(audit(self.path, determinant=["k"], dependent=["v"])["passed"])
            with self.assertRaisesRegex(AuditError, "sqlite storage is unavailable"):
                self.run_disk()
        self.assert_clean()

    def test_header_only_parity(self):
        self.rows([])
        self.assertEqual(self.run_disk(), audit(self.path, determinant=["k"], dependent=["v"]))
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
