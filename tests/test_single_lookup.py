import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, Limits, audit, audit_many
from depwitness.disk import _DiskGroups


class SingleLookupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "input.csv"
        self.temp = Path(self.temporary.name) / "indexes"
        self.temp.mkdir()

    def rows(self, rows):
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows([("k", "v"), *rows])

    def run_counted(self, rows, **options):
        self.rows(rows)
        statements, stored = Counter(), []
        execute, store = _DiskGroups.execute, _DiskGroups.__setitem__

        def count(groups, sql, parameters=()):
            statements[sql] += 1
            return execute(groups, sql, parameters)

        def record(groups, key, group):
            stored.append(group[0])
            return store(groups, key, group)

        with (
            patch.object(_DiskGroups, "execute", count),
            patch.object(_DiskGroups, "__setitem__", record),
        ):
            report = audit(
                self.path,
                determinant=["k"],
                dependent=["v"],
                storage="sqlite",
                temp_dir=self.temp,
                **options,
            )
        self.assertEqual(list(self.temp.iterdir()), [])
        return report, statements, stored

    def test_no_membership_probe_or_empty_persistence(self):
        rows = [(str(i), "x") for i in range(100)] * 3
        report, statements, stored = self.run_counted(rows)
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"]["determinant_groups"], 100)
        self.assertEqual(len(stored), 300)
        self.assertNotIn(0, stored)
        self.assertEqual(statements["SELECT 1 FROM groups WHERE k = ?"], 0)
        # One lookup per input row; summary streams group payloads directly.
        self.assertEqual(
            statements["SELECT n, representative, promoted, first_record FROM groups WHERE k = ?"],
            300,
        )

    def test_first_row_and_repeat_retain_counts_and_ordinals(self):
        rows = [("a", "x")] * 5 + [("b", "p")] * 4 + [("a", "y")] * 3
        rows += [("a", "z")] * 2 + [("b", "p")] * 2
        for cap in (0, 1, 1000):
            with self.subTest(cap=cap):
                disk, _, stored = self.run_counted(rows, examples=cap)
                memory = audit(self.path, determinant=["k"], dependent=["v"], examples=cap)
                self.assertEqual(disk, memory)
                self.assertEqual(len(stored), len(rows))
                self.assertEqual(disk["counts"]["conflicting_record_pairs"], 31)
                self.assertEqual(disk["counts"]["minimum_record_removals"], 5)
                if cap:
                    self.assertEqual(disk["examples"][0]["first_record"], 1)
                    self.assertEqual(disk["examples"][0]["conflicting_record"], 10)

    def test_group_caps_count_first_completed_group(self):
        self.rows([("a", "x"), ("a", "y"), ("b", "z")])
        rule = {"determinant": ["k"], "dependent": ["v"]}
        for storage in ("memory", "sqlite"):
            with self.subTest(storage=storage):
                with self.assertRaisesRegex(AuditError, "determinant group limit"):
                    audit(self.path, limits=Limits(max_groups=1), storage=storage, **rule)
                with self.assertRaisesRegex(AuditError, "batch total determinant group"):
                    audit_many(
                        self.path,
                        rules=[rule, rule],
                        max_total_groups=3,
                        storage=storage,
                        temp_dir=self.temp if storage == "sqlite" else None,
                    )
                batch = audit_many(
                    self.path, rules=[rule, rule], max_total_groups=4, storage=storage
                )
                self.assertEqual(batch["rules"][0], batch["rules"][1])
                self.assertEqual(batch["rules"][0]["counts"]["determinant_groups"], 2)
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_group_read_failure_is_not_treated_as_a_missing_key(self):
        self.rows([("a", "x")])
        original = _DiskGroups.__getitem__
        calls = []

        def fail_once(groups, key):
            if not calls:
                calls.append(True)
                raise AuditError("read failed")
            return original(groups, key)

        with (
            patch.object(_DiskGroups, "__getitem__", fail_once),
            self.assertRaisesRegex(AuditError, "read failed"),
        ):
            audit(
                self.path,
                determinant=["k"],
                dependent=["v"],
                storage="sqlite",
                temp_dir=self.temp,
            )
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_summary_payloads_stream_without_key_roundtrips(self):
        from depwitness.disk import sqlite_groups

        huge = 2**100
        with sqlite_groups(self.temp) as groups:
            groups[("é",)] = [huge, ("1.00",), None, 3]
            groups[("b",)] = [5, ("x",), Counter({("x",): 3, ("y",): 2}), 7]
            statements = []
            execute = groups.execute

            def count(sql, parameters=()):
                statements.append(sql)
                return execute(sql, parameters)

            with (
                patch.object(groups, "execute", count),
                patch.object(
                    _DiskGroups, "__getitem__", side_effect=AssertionError("summary lookup")
                ),
            ):
                rows = list(groups.values())
                self.assertEqual(rows[0], [huge, ("1.00",), None, 3])
                self.assertEqual(rows[1][:2], [5, ("x",)])
                self.assertEqual(rows[1][3], 7)
                self.assertEqual(sorted(rows[1][2].values()), [2, 3])
            self.assertEqual(
                statements.count(
                    "SELECT k, n, representative, promoted, first_record FROM groups ORDER BY rowid"
                ),
                1,
            )
        self.assertEqual(list(self.temp.iterdir()), [])
