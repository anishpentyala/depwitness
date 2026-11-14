"""Incremental source reads preserve complete-file validation and receipts."""

import csv
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, Limits, __version__, audit


class StreamingInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input.csv"

    def valid(self, **kwargs):
        try:
            return audit(self.path, determinant=["a"], dependent=["b"], **kwargs)
        except (AuditError, ValueError, AssertionError) as exc:
            self.fail(f"valid input raised {type(exc).__name__}: {exc}")

    def check(self, raw, **kwargs):
        self.path.write_bytes(raw)
        result = self.valid(**kwargs)
        self.assertEqual(
            result["input"], {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        )
        return result

    def test_runtime_version_matches_distribution(self):
        self.assertEqual(__version__, "0.1.2")

    def test_bounded_reads_and_read_once_receipt(self):
        raw = b"a,b,unused\r\n" + b"same,value," + b"x" * 1000 + b"\r\n"
        raw += (b"same,value," + b"y" * 1000 + b"\r\n") * 100
        calls = []

        class RecordingStream(io.BytesIO):
            def read(self, size=-1):
                self_test.assertGreater(size, 0)
                self_test.assertLessEqual(size, 8192)
                calls.append(size)
                return super().read(size)

        self_test = self
        stream = RecordingStream(raw)
        with patch("depwitness.core.Path.open", return_value=stream) as opened:
            result = self.valid()
        self.assertEqual(opened.call_count, 1)
        self.assertTrue(stream.closed)
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"]["records"], 101)
        self.assertEqual(result["input"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["input"]["bytes"], len(raw))
        self.assertGreater(len(calls), 2)
        self.assertTrue(all(0 < size <= 8192 for size in calls), calls)

    def test_chunk_split_utf8_bom_crlf_and_quoted_newlines(self):
        # Deliberately split either a multibyte code point or quoted CRLF at
        # the 8192-byte raw buffer boundary, including the optional UTF-8 BOM.
        for marker in ("€", "\r\n𐀀"):
            for delimiter in (",", "é"):

                def encode(padding, delimiter=delimiter):
                    text = io.StringIO(newline="")
                    w = csv.writer(text, delimiter=delimiter, lineterminator="\r\n")
                    w.writerow(["a", "b", "unused"])
                    w.writerow(["same", "value", "x" * padding + "€\r\n𐀀"])
                    w.writerow(["same", "other", "done"])
                    return b"\xef\xbb\xbf" + text.getvalue().encode()

                target = marker.encode()
                padding = 8191 - encode(0).index(target)
                raw = encode(padding)
                self.assertEqual(raw.index(target), 8191)
                with self.subTest(marker=marker, delimiter=delimiter):
                    row = self.check(
                        raw,
                        delimiter=delimiter,
                        examples=1,
                        limits=Limits(max_field_chars=10000),
                    )
                    self.assertEqual(row["counts"]["conflicting_record_pairs"], 1)
                    self.assertEqual(row["examples"][0]["conflicting_record"], 2)

    def test_complete_tail_validation_with_default_or_filled_evidence(self):
        valid = b"a,b,c\nkey,one,pad\nkey,two,pad\n" + b"key,one,pad\n" * 2000
        for tail in (b"key,one,\x00\n", b"key,one,\xff\n", b'key,one,"unterminated'):
            for examples in (0, 1):
                with self.subTest(tail=tail, examples=examples):
                    self.path.write_bytes(valid + tail)
                    with self.assertRaises(AuditError):
                        audit(self.path, determinant=["a"], dependent=["b"], examples=examples)

    def test_exact_byte_limit_and_over_limit_at_eof(self):
        raw = b"\xef\xbb\xbfa,b\r\nkey,value\r\n"
        row = self.check(raw, limits=Limits(max_bytes=len(raw)))
        self.assertEqual(row["counts"]["records"], 1)
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(AuditError, "byte limit"):
            audit(
                self.path, determinant=["a"], dependent=["b"], limits=Limits(max_bytes=len(raw) - 1)
            )
        self.check(b"a,b\n", limits=Limits(max_bytes=4))

    def test_read_failure_after_valid_buffer_is_not_partial_success(self):
        class FailsLate(io.BytesIO):
            def read(self, size=-1):
                if self.tell() > 0:
                    raise OSError("late source failure")
                return super().read(min(size, 8192))

        for examples in (0, 1):
            stream = FailsLate(b"a,b\nk,v\nk,w\n" + b"k,v\n" * 5000)
            with (
                patch("depwitness.core.Path.open", return_value=stream),
                self.assertRaises(AuditError),
            ):
                audit(self.path, determinant=["a"], dependent=["b"], examples=examples)
            self.assertTrue(stream.closed)
