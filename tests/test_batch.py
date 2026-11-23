import contextlib
import csv
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, Limits, audit, audit_many
from depwitness.__main__ import main


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data.csv"
        self.rules = [
            {"determinant": ["a"], "dependent": ["b"]},
            {"determinant": ["b"], "dependent": ["c"]},
            {"determinant": ["a", "b"], "dependent": ["c"]},
        ]
        self.write([["a", "b", "c"], ["1", "x", "p"], ["1", "x", "q"], ["2", "x", "p"]])

    def write(self, rows):
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)

    def batch(self, **kwargs):
        return audit_many(self.path, rules=self.rules, **kwargs)

    def test_complete_reports_equal_single_rule_calls_both_backends(self):
        for storage in ["memory", "sqlite"]:
            with self.subTest(storage=storage):
                actual = self.batch(storage=storage, examples=2)
                self.assertEqual(
                    actual["rules"],
                    [audit(self.path, **r, storage=storage, examples=2) for r in self.rules],
                )
                self.assertFalse(actual["passed"])

    def test_one_open_and_one_complete_read(self):
        from depwitness.core import _open_regular

        original = _open_regular
        opened = []

        def counted(path, *args, **kwargs):
            if path == self.path:
                opened.append(args)
            return original(path, *args, **kwargs)

        with patch("depwitness.core._open_regular", counted):
            result = self.batch()
        self.assertEqual(opened, [()])
        self.assertEqual(result["rules"][0]["input"]["bytes"], self.path.stat().st_size)
        self.assertTrue(all(r["input"] == result["rules"][0]["input"] for r in result["rules"]))

    def test_generated_parity(self):
        rng = random.Random(569120)
        for trial in range(100):
            rows = [["a", "b", "c"]] + [
                [rng.choice(["", "01", "1", "é", "NULL", "a\nb"]) for _ in range(3)]
                for _ in range(rng.randrange(35))
            ]
            self.write(rows)
            expected = [audit(self.path, **r, examples=3) for r in self.rules]
            for storage in ["memory", "sqlite"]:
                with self.subTest(trial=trial, storage=storage):
                    actual = self.batch(storage=storage, examples=3)
                    self.assertEqual(actual["rules"], expected)
                    self.assertEqual(actual["passed"], all(r["passed"] for r in expected))

    def test_late_invalid_row_rejects_batch_and_cleans_sqlite(self):
        self.path.write_bytes(b"a,b,c\n1,x,p\n1,y,q\n2,z,r\ninvalid\n")
        for storage in ["memory", "sqlite"]:
            with self.subTest(storage=storage):
                opts = {"storage": storage}
                if storage == "sqlite":
                    opts["temp_dir"] = self.tmp.name
                with self.assertRaises(AuditError):
                    self.batch(**opts)
                self.assertEqual(list(Path(self.tmp.name).glob("depwitness-*")), [])

    def test_late_invalid_utf8_and_nul_no_reports(self):
        for suffix in [b"\xff", b"\x00"]:
            self.path.write_bytes(b"a,b,c\n1,x,p\n" + suffix)
            with self.assertRaises(AuditError):
                self.batch()

    def test_bad_later_rule_cleans_open_indexes(self):
        rules = self.rules + [{"determinant": ["missing"], "dependent": ["b"]}]
        with self.assertRaises(AuditError):
            audit_many(self.path, rules=rules, storage="sqlite", temp_dir=self.tmp.name)
        self.assertEqual(list(Path(self.tmp.name).glob("depwitness-*")), [])

    def test_invalid_policies_before_input_open(self):
        bad = [
            [],
            None,
            {},
            [None],
            [{"determinant": ["a"], "dependent": ["a"]}],
            [dict(self.rules[0], typo=1)],
            [self.rules[0]] * 101,
        ]
        for rules in bad:
            with (
                self.subTest(rules=str(rules)[:70]),
                patch.object(Path, "open", side_effect=AssertionError("must validate first")),
                self.assertRaises(AuditError),
            ):
                audit_many(self.path, rules=rules)

    def test_batch_group_cap_and_per_rule_group_cap(self):
        for storage in ["memory", "sqlite"]:
            with self.subTest(storage=storage):
                with self.assertRaisesRegex(AuditError, "batch total"):
                    self.batch(storage=storage, max_total_groups=2)
                with self.assertRaisesRegex(AuditError, "^determinant group"):
                    self.batch(storage=storage, limits=Limits(max_groups=1))
                self.assertEqual(len(self.batch(storage=storage, max_total_groups=5)["rules"]), 3)

    def test_later_storage_setup_failure_cleans_prior_index(self):
        from contextlib import contextmanager

        from depwitness import core

        original = core._groups
        opened = []

        @contextmanager
        def fail_second(storage, temp_dir, cleanup_stack=None):
            if opened:
                raise AuditError("injected second index setup failure")
            opened.append(True)
            with original(storage, temp_dir, cleanup_stack) as groups:
                yield groups

        with patch.object(core, "_groups", fail_second), self.assertRaises(AuditError):
            self.batch(storage="sqlite", temp_dir=self.tmp.name)
        self.assertEqual(list(Path(self.tmp.name).glob("depwitness-*")), [])

    def test_last_rule_summary_failure_never_emits_cli_report(self):
        from depwitness import core

        original = core._RuleState.report

        def last_fails(state, *args):
            if state.determinant == ("b",):
                raise AuditError("injected last summary failure")
            return original(state, *args)

        flags = [arg for rule in self.rules[:2] for arg in ["--rule", json.dumps(rule)]]
        with patch.object(core._RuleState, "report", last_fails):
            code, out, err = self.cli(flags)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("last summary failure", err)

    def test_invalid_shared_options_and_late_byte_cap(self):
        for options in [
            {"examples": True},
            {"examples": 1001},
            {"delimiter": ""},
            {"storage": "unknown"},
            {"temp_dir": "/unused"},
            {"limits": Limits(max_bytes=self.path.stat().st_size - 1)},
        ]:
            with self.subTest(options=options), self.assertRaises(AuditError):
                self.batch(**options)

    def test_cli_deep_and_oversized_rule_is_a_clean_error(self):
        for value in ["[" * 2000, "x" * 262145]:
            code, out, err = self.cli(["--rule", value])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("depwitness:", err)

    def test_total_cap_rejects_bool_and_zero(self):
        for value in [True, 0, -1, 2.5, None]:
            with self.assertRaises(AuditError):
                self.batch(max_total_groups=value)

    def test_header_only_and_duplicate_rules_order(self):
        self.write([["a", "b", "c"]])
        result = audit_many(self.path, rules=[self.rules[2], self.rules[0], self.rules[2]])
        self.assertTrue(result["passed"])
        self.assertEqual(
            [r["policy"]["determinant"] for r in result["rules"]], [["a", "b"], ["a"], ["a", "b"]]
        )

    def cli(self, flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.path), *flags])
        return code, out.getvalue(), err.getvalue()

    def test_cli_batch_and_existing_single_rule_reports(self):
        flags = [arg for rule in self.rules for arg in ["--rule", json.dumps(rule)]]
        code, out, err = self.cli(flags)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), self.batch())
        self.assertEqual(err, "")
        code, out, err = self.cli(["--determinant", "a", "--dependent", "b"])
        self.assertEqual(json.loads(out), audit(self.path, **self.rules[0]))

    def test_cli_invalid_rules_produce_no_partial_json(self):
        for flags in [
            ["--rule", "{"],
            ["--rule", "null"],
            ["--rule", '{"determinant":["a"],"determinant":["b"],"dependent":["c"]}'],
            ["--rule", json.dumps(self.rules[0]), "--determinant", "a"],
            ["--max-total-groups", "5", "--determinant", "a", "--dependent", "b"],
        ]:
            with self.subTest(flags=flags):
                code, out, err = self.cli(flags)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("depwitness:", err)

    def test_cli_pass_exit_zero(self):
        self.write([["a", "b", "c"], ["1", "x", "p"]])
        code, out, _err = self.cli(["--rule", json.dumps(self.rules[0])])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["passed"])


if __name__ == "__main__":
    unittest.main()
