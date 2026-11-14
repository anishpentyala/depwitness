import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from depwitness import audit


class CompactTests(unittest.TestCase):
    def run_rows(self, rows, examples=0):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            with path.open("w", newline="") as stream:
                csv.writer(stream).writerows([["k", "v"], *rows])
            with patch("depwitness.core.Counter", wraps=Counter) as factory:
                report = audit(path, determinant=["k"], dependent=["v"], examples=examples)
            return report, factory

    def test_consistent_groups_do_not_allocate_counters(self):
        for cap in [0, 1, 1000]:
            rows = [(str(i), "x") for i in range(100)] * 3
            report, factory = self.run_rows(rows, cap)
            self.assertTrue(report["passed"])
            self.assertEqual(report["counts"]["repeated_determinant_groups"], 100)
            self.assertEqual(factory.call_count, 0)

    def test_only_conflicting_groups_promote_once(self):
        rows = [("a", "x")] * 5 + [("b", "p")] * 4 + [("a", "y")] * 3
        rows += [("a", "z")] * 2 + [("b", "p")] * 2
        for cap in [0, 1, 1000]:
            report, factory = self.run_rows(rows, cap)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(factory.call_args.args, ({("x",): 5},))
            self.assertEqual(report["counts"]["conflicting_record_pairs"], 31)
            self.assertEqual(report["counts"]["affected_records"], 10)
            self.assertEqual(report["counts"]["minimum_record_removals"], 5)
            if cap:
                self.assertEqual(report["examples"][0]["first_record"], 1)
                self.assertEqual(report["examples"][0]["conflicting_record"], 10)

    def test_return_to_representative_after_promotion(self):
        report, factory = self.run_rows(
            [("a", "x"), ("a", "y"), ("a", "x"), ("a", "y"), ("a", "x")], 1
        )
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(report["counts"]["conflicting_record_pairs"], 6)
        self.assertEqual(report["counts"]["minimum_record_removals"], 2)

    def test_many_group_promotions_and_no_duplicate_examples(self):
        rows = [(str(i), v) for v in ["x", "y", "z", "x"] for i in range(100)]
        report, factory = self.run_rows(rows, 3)
        self.assertEqual(factory.call_count, 100)
        self.assertEqual(report["counts"]["conflicting_record_pairs"], 500)
        self.assertEqual(report["counts"]["minimum_record_removals"], 200)
        self.assertEqual(
            [x["determinant_values"] for x in report["examples"]], [["0"], ["1"], ["2"]]
        )
        self.assertEqual(report["violating_groups_without_example"], 97)


if __name__ == "__main__":
    unittest.main()
