"""Promoted group updates reuse the RHS count instead of rereading SQLite."""

import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, audit, audit_many
from depwitness.core import Limits, _RuleState
from depwitness.disk import _DiskCounter, _DiskGroups


class FrequencyLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.csv"
        self.storage = self.root / "indexes"
        self.storage.mkdir()
        self.rule = {"determinant": ["k"], "dependent": ["v"]}

    def test_one_frequency_select_per_previously_promoted_row(self):
        rows = [("a", "x"), ("a", "y"), ("a", "x"), ("a", "z"), ("a", "z")]
        rows += [("b", "p"), ("b", "p"), ("b", "q"), ("b", "q")]
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows([("k", "v"), *rows])
        original = _DiskGroups.execute
        statements = Counter()

        def count(groups, sql, parameters=()):
            statements[sql] += 1
            return original(groups, sql, parameters)

        with patch.object(_DiskGroups, "execute", count):
            disk = audit(self.path, storage="sqlite", temp_dir=self.storage, **self.rule)
        self.assertEqual(disk, audit(self.path, **self.rule))
        self.assertEqual(statements["SELECT n FROM frequencies WHERE k = ? AND v = ?"], 4)
        self.assertEqual(disk["counts"]["conflicting_record_pairs"], 12)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_exact_python_integer_arithmetic_above_sqlite_range(self):
        huge = 2**100
        groups = {("a",): [huge + 3, ("x",), Counter({("x",): huge, ("y",): 3}), None]}
        state = _RuleState(("k",), ("v",), 0, Limits(), groups)
        state.bind(["k", "v"])
        state.add(["a", "x"], 1)
        state.add(["a", "z"], 2)
        self.assertEqual(state.pairs, 3 + huge + 4)
        self.assertEqual(groups[("a",)][2], Counter({("x",): huge + 1, ("y",): 3, ("z",): 1}))

    def test_frequency_read_failure_rejects_single_and_batch_and_cleans_up(self):
        self.path.write_text("k,v\na,x\na,y\na,x\n", encoding="utf-8")
        for batch in (False, True):
            with (
                patch.object(_DiskCounter, "__getitem__", side_effect=AuditError("read failed")),
                self.assertRaisesRegex(AuditError, "read failed"),
            ):
                if batch:
                    audit_many(
                        self.path, rules=[self.rule] * 2, storage="sqlite", temp_dir=self.storage
                    )
                else:
                    audit(self.path, **self.rule, storage="sqlite", temp_dir=self.storage)
            self.assertEqual(list(self.storage.iterdir()), [])
