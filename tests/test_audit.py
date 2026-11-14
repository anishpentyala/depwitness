import contextlib
import csv
import hashlib
import io
import itertools
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, Limits, audit
from depwitness.__main__ import main


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.csv"
        self.write([["k", "v"], ["a", "x"], ["a", "y"]])

    def write(self, rows, delimiter=","):
        with self.path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=delimiter).writerows(rows)

    def run_audit(self, **kwargs):
        return audit(self.path, determinant=["k"], dependent=["v"], **kwargs)

    def cli(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.path), "--determinant", "k", "--dependent", "v", *flags])
        return code, out.getvalue(), err.getvalue()

    def test_basic_conflict(self):
        r = self.run_audit()
        self.assertFalse(r["passed"])
        self.assertEqual(
            r["counts"],
            {
                "records": 2,
                "determinant_groups": 1,
                "repeated_determinant_groups": 1,
                "violating_groups": 1,
                "affected_records": 2,
                "conflicting_record_pairs": 1,
                "minimum_record_removals": 1,
            },
        )

    def test_duplicate_rows_are_not_fd_violations(self):
        self.write([["k", "v"], ["a", "x"], ["a", "x"]])
        r = self.run_audit()
        self.assertTrue(r["passed"])
        self.assertEqual(r["counts"]["repeated_determinant_groups"], 1)
        for k in [
            "violating_groups",
            "affected_records",
            "conflicting_record_pairs",
            "minimum_record_removals",
        ]:
            self.assertEqual(r["counts"][k], 0)

    def test_pair_counts_multiplicity_and_all_affected(self):
        self.write([["k", "v"]] + [["a", "x"]] * 3 + [["a", "y"]] * 2 + [["b", "q"]])
        r = self.run_audit()["counts"]
        self.assertEqual(r["conflicting_record_pairs"], 6)
        self.assertEqual(r["affected_records"], 5)
        self.assertEqual(r["minimum_record_removals"], 2)

    def test_three_versions_and_majority_ties(self):
        self.write([["k", "v"]] + [["a", v] for v in "xxyyzz"])
        r = self.run_audit()["counts"]
        self.assertEqual(r["conflicting_record_pairs"], 12)
        self.assertEqual(r["minimum_record_removals"], 4)
        self.assertEqual(r["affected_records"], 6)

    def test_multiple_groups(self):
        self.write(
            [["k", "v"]]
            + [[k, v] for k, v in [("a", "x"), ("b", "x"), ("a", "y"), ("b", "z"), ("c", "q")]]
        )
        r = self.run_audit()["counts"]
        self.assertEqual(
            (
                r["determinant_groups"],
                r["violating_groups"],
                r["affected_records"],
                r["conflicting_record_pairs"],
            ),
            (3, 2, 4, 2),
        )

    def test_composite_tuples_not_joined_strings(self):
        self.write(
            [
                ["a", "b", "x", "y"],
                ["a|b", "c", "d|e", "f"],
                ["a", "b|c", "d", "e|f"],
                ["a|b", "c", "d", "e|f"],
            ]
        )
        r = audit(self.path, determinant=["a", "b"], dependent=["x", "y"])
        self.assertEqual(r["counts"]["determinant_groups"], 2)
        self.assertEqual(r["counts"]["conflicting_record_pairs"], 1)

    def test_selected_column_order(self):
        self.write(
            [["v", "unused", "k", "v2", "k2"], ["x", "1", "a", "p", "b"], ["y", "2", "a", "p", "b"]]
        )
        r = audit(self.path, determinant=["k2", "k"], dependent=["v2", "v"], examples=1)
        self.assertEqual(len(r["examples"]), 1)
        e = r["examples"][0]
        self.assertEqual(e["determinant_values"], ["b", "a"])
        self.assertEqual(e["first_dependent_values"], ["p", "x"])

    def test_unselected_differences_do_not_violate(self):
        self.write([["k", "v", "ignore"], ["a", "x", "one"], ["a", "x", "two"]])
        self.assertTrue(self.run_audit()["passed"])

    def test_exact_strings_no_coercion(self):
        self.write(
            [
                ["k", "v"],
                ["01", "x"],
                ["1", "y"],
                [" 1", "z"],
                ["é", "a"],
                ["e\u0301", "b"],
                ["A", "x"],
                ["a", "y"],
            ]
        )
        r = self.run_audit()["counts"]
        self.assertEqual(r["determinant_groups"], 7)
        self.assertEqual(r["violating_groups"], 0)

    def test_empty_and_null_spellings_are_literal(self):
        self.write([["k", "v"], ["", ""], ["", "NULL"], ["NA", "x"], ["NULL", "x"]])
        r = self.run_audit(examples=1)
        self.assertEqual(r["counts"]["records"], 4)
        self.assertEqual(r["counts"]["conflicting_record_pairs"], 1)
        self.assertEqual(r["examples"][0]["determinant_values"], [""])
        self.assertEqual(r["examples"][0]["first_dependent_values"], [""])

    def test_whitespace_values_are_valid_and_distinct(self):
        self.write([["k", "v"], [" ", " "], [" ", ""], ["", " "]])
        self.assertEqual(self.run_audit()["counts"]["conflicting_record_pairs"], 1)

    def test_witnesses_first_conflict_discovery_not_group_order(self):
        self.write(
            [["k", "v"], ["a", "x"], ["b", "p"], ["b", "q"], ["a", "x"], ["a", "y"], ["b", "r"]]
        )
        r = self.run_audit(examples=2)
        self.assertEqual(
            r["examples"],
            [
                {
                    "determinant_values": ["b"],
                    "first_record": 2,
                    "first_dependent_values": ["p"],
                    "conflicting_record": 3,
                    "conflicting_dependent_values": ["q"],
                },
                {
                    "determinant_values": ["a"],
                    "first_record": 1,
                    "first_dependent_values": ["x"],
                    "conflicting_record": 5,
                    "conflicting_dependent_values": ["y"],
                },
            ],
        )
        self.assertEqual(r["violating_groups_without_example"], 0)

    def test_example_caps_do_not_change_counts(self):
        self.write([["k", "v"], ["a", "x"], ["a", "y"], ["b", "z"], ["b", "p"]])
        base = self.run_audit()["counts"]
        for cap in [0, 1, 2, 1000]:
            r = self.run_audit(examples=cap)
            self.assertEqual(r["counts"], base)
            self.assertEqual(len(r["examples"]), min(cap, 2))
            self.assertEqual(r["violating_groups_without_example"], 2 - min(cap, 2))

    def test_default_no_raw_values(self):
        self.write([["k", "v"], ["SECRETKEY", "SECRETA"], ["SECRETKEY", "SECRETB"]])
        encoded = json.dumps(self.run_audit())
        self.assertNotIn("SECRET", encoded)
        self.assertEqual(self.run_audit()["examples"], [])

    def test_header_only_vacuous_pass(self):
        self.write([["k", "v"]])
        r = self.run_audit(examples=10)
        self.assertTrue(r["passed"])
        self.assertTrue(all(x == 0 for x in r["counts"].values()))
        self.assertEqual(r["examples"], [])

    def test_multiline_record_ordinals_not_lines(self):
        self.write([["k", "v"], ["a\nb", "x\ny"], ["a\nb", "z"]])
        r = self.run_audit(examples=1)
        self.assertEqual(
            (r["examples"][0]["first_record"], r["examples"][0]["conflicting_record"]), (1, 2)
        )
        self.assertEqual(r["examples"][0]["determinant_values"], ["a\nb"])

    def test_custom_delimiter_and_quotes(self):
        self.write([["k", "v"], ["a;b", '"x"'], ["a;b", "y"]], delimiter=";")
        self.assertEqual(self.run_audit(delimiter=";")["counts"]["conflicting_record_pairs"], 1)

    def test_bom_and_exact_byte_receipt(self):
        raw = b"\xef\xbb\xbfk,v\r\na,x\r\na,y\r\n"
        self.path.write_bytes(raw)
        r = self.run_audit()
        self.assertEqual(r["input"], {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})

    def test_input_unchanged(self):
        before = self.path.read_bytes()
        self.run_audit(examples=1)
        self.assertEqual(before, self.path.read_bytes())

    def test_invalid_header(self):
        for raw in ["", "\n", "k,k\na,x\n", "k, \na,x\n", "k,x\na,x\n"]:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(AuditError):
                    self.run_audit()

    def test_invalid_full_input_not_just_selected(self):
        for raw in [
            b"k,v\na,x\na\n",
            b"k,v\na,x\n\n",
            b"k,v\na,x,y\n",
            b'k,v\na,x\n"unterminated',
            b"k,v\na,x\na,\xff\n",
            b"k,v\na,x\na,\x00\n",
        ]:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(AuditError):
                    self.run_audit()

    def test_unselected_oversized_field_fails(self):
        self.write([["k", "v", "extra"], ["a", "x", "z" * 11]])
        with self.assertRaises(AuditError):
            self.run_audit(limits=Limits(max_field_chars=10))

    def test_missing_and_directory_input(self):
        for p in [self.path.parent / "missing", self.path.parent]:
            with self.assertRaises(AuditError):
                audit(p, determinant=["k"], dependent=["v"])

    def test_invalid_input_path_type(self):
        for path in [None, 3, b"input.csv", []]:
            with self.subTest(path=path), self.assertRaises(AuditError):
                audit(path, determinant=["k"], dependent=["v"])

    def test_composite_dependent_minimum_uses_joint_tuple(self):
        self.write([["k", "x", "y"], ["a", "0", "0"], ["a", "0", "1"], ["a", "1", "0"]])
        r = audit(self.path, determinant=["k"], dependent=["x", "y"])
        self.assertEqual(r["counts"]["minimum_record_removals"], 2)
        self.assertEqual(r["counts"]["conflicting_record_pairs"], 3)

    def test_limit_boundaries(self):
        size = len(self.path.read_bytes())
        self.run_audit(
            limits=Limits(
                max_bytes=size, max_records=2, max_groups=1, max_columns=2, max_field_chars=1
            )
        )
        for limits in [Limits(max_bytes=size - 1), Limits(max_records=1), Limits(max_columns=1)]:
            with self.subTest(limits=limits), self.assertRaises(AuditError):
                self.run_audit(limits=limits)
        self.write([["k", "v"], ["a", "x"], ["b", "x"]])
        with self.assertRaises(AuditError):
            self.run_audit(limits=Limits(max_groups=1))

    def test_invalid_limits(self):
        for name in vars(Limits()):
            for bad in [0, -1, True, 1.0, "3", None]:
                with self.subTest(name=name, bad=bad), self.assertRaises(AuditError):
                    Limits(**{name: bad})
        with self.assertRaises(AuditError):
            self.run_audit(limits={})

    def test_invalid_columns(self):
        for bad in [[], (), "k", {"k"}, [None], [""], [" "], ["k", "k"]]:
            for role in ["determinant", "dependent"]:
                kw = {"determinant": ["k"], "dependent": ["v"]}
                kw[role] = bad
                with self.subTest(role=role, bad=bad), self.assertRaises(AuditError):
                    audit(self.path, **kw)
        with self.assertRaises(AuditError):
            audit(self.path, determinant=["k"], dependent=["k"])

    def test_invalid_examples_and_delimiter(self):
        for examples in [-1, 1001, True, 1.0, None, "1"]:
            with self.subTest(examples=examples), self.assertRaises(AuditError):
                self.run_audit(examples=examples)
        for delimiter in ["", ";;", "\n", "\r", "\x00", '"', "\ufeff", None, 3]:
            with self.subTest(delimiter=delimiter), self.assertRaises(AuditError):
                self.run_audit(delimiter=delimiter)

    def test_cli_complete_violation_and_pass(self):
        code, out, err = self.cli("--examples", "1")
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(json.loads(out), self.run_audit(examples=1))
        self.write([["k", "v"], ["a", "x"], ["b", "y"]])
        code, out, err = self.cli()
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(json.loads(out)["passed"])

    def test_cli_no_partial_report_on_late_errors(self):
        self.path.write_bytes(b"k,v\na,x\na,y\nbad\n")
        code, out, err = self.cli("--examples", "1")
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("depwitness:"))

    def test_cli_limits_and_bad_args(self):
        for flags in [
            ("--max-records", "1"),
            ("--max-bytes", "1"),
            ("--examples", "-1"),
            ("--max-groups", "0"),
            ("--delimiter", "xx"),
        ]:
            code, out, err = self.cli(*flags)
            self.assertEqual((code, out), (2, ""))
            self.assertTrue(err)
        with self.assertRaises(SystemExit) as cm:
            self.cli("--examples", "n")
        self.assertEqual(cm.exception.code, 2)

    def test_cli_memory_and_pipe_errors(self):
        with patch("depwitness.__main__.audit", side_effect=MemoryError):
            code, out, err = self.cli()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("insufficient memory", err)
        with patch("depwitness.__main__.sys.stdout.write", side_effect=BrokenPipeError):
            self.assertEqual(main([str(self.path), "--determinant", "k", "--dependent", "v"]), 2)

    def test_dense_counts_without_pair_materialization(self):
        self.write([["k", "v"]] + [["a", str(i % 2)] for i in range(10000)])
        r = self.run_audit(examples=1)
        self.assertEqual(r["counts"]["conflicting_record_pairs"], 25000000)
        self.assertEqual(r["counts"]["minimum_record_removals"], 5000)
        self.assertEqual(len(r["examples"]), 1)

    def test_independent_random_all_pairs_and_bruteforce_removals(self):
        rng = random.Random(99173)
        for case in range(200):
            rows = [
                (rng.choice(["", "a", "b", "01", "1"]), rng.choice(["", "x", "y"]))
                for _ in range(rng.randrange(9))
            ]
            self.write([["k", "v"], *rows])
            r = self.run_audit(examples=3)
            conflicts = [
                (i, j)
                for i in range(len(rows))
                for j in range(i + 1, len(rows))
                if rows[i][0] == rows[j][0] and rows[i][1] != rows[j][1]
            ]
            affected = {i for p in conflicts for i in p}
            keys = {rows[i][0] for i in affected}
            # Exhaust all deletion subsets: no frequency/max formula in this oracle.
            minimum = len(rows)
            for bits in itertools.product([False, True], repeat=len(rows)):
                if not any(not bits[i] and not bits[j] for i, j in conflicts):
                    minimum = min(minimum, sum(bits))
            with self.subTest(case=case):
                self.assertEqual(r["counts"]["conflicting_record_pairs"], len(conflicts))
                self.assertEqual(r["counts"]["affected_records"], len(affected))
                self.assertEqual(r["counts"]["violating_groups"], len(keys))
                self.assertEqual(r["counts"]["minimum_record_removals"], minimum)
                self.assertEqual(r["passed"], not conflicts)
                for e in r["examples"]:
                    a, b = e["first_record"] - 1, e["conflicting_record"] - 1
                    self.assertIn((a, b), conflicts)
                    self.assertEqual(e["determinant_values"], [rows[a][0]])
                    self.assertEqual(e["first_dependent_values"], [rows[a][1]])
                    self.assertEqual(e["conflicting_dependent_values"], [rows[b][1]])


if __name__ == "__main__":
    unittest.main()
