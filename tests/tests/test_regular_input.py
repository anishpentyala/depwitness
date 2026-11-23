"""Refuse streaming special inputs without reading or waiting for producers."""

import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depwitness import AuditError, audit, audit_many
from depwitness.core import _open_regular


class RegularInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.csv"
        self.raw = b"a,b\nx,1\nx,2\n"
        self.path.write_bytes(self.raw)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self.rule = {"determinant": ["a"], "dependent": ["b"]}

    def runs(self, path):
        for storage in ("memory", "sqlite"):
            kwargs = {"storage": storage}
            if storage == "sqlite":
                kwargs["temp_dir"] = self.storage
            yield lambda kwargs=kwargs: audit(path, **self.rule, **kwargs)
            yield lambda kwargs=kwargs: audit_many(path, rules=[self.rule] * 2, **kwargs)

    def test_regular_and_regular_symlink_receipts_all_modes(self):
        link = self.root / "link.csv"
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        for path in (self.path, link):
            for run in self.runs(path):
                result = run()
                reports = result.get("rules", [result])
                for report in reports:
                    self.assertFalse(report["passed"])
                    self.assertEqual(
                        report["input"],
                        {
                            "sha256": hashlib.sha256(self.raw).hexdigest(),
                            "bytes": len(self.raw),
                        },
                    )
                self.assertEqual(list(self.storage.iterdir()), [])

    def test_directory_and_missing_paths_fail_all_modes_and_cleanup(self):
        for path in (self.root, self.root / "missing.csv"):
            for run in self.runs(path):
                with self.assertRaises(AuditError):
                    run()
                self.assertEqual(list(self.storage.iterdir()), [])

    @unittest.skipUnless(hasattr(os, "O_NONBLOCK") and hasattr(os, "mkfifo"), "POSIX FIFO")
    def test_fifo_without_producer_cli_all_modes_and_cleanup(self):
        fifo = self.root / "pipe.csv"
        os.mkfifo(fifo)
        for storage in ("memory", "sqlite"):
            for batch in (False, True):
                cmd = [sys.executable, "-m", "depwitness", str(fifo), "--storage", storage]
                if storage == "sqlite":
                    cmd += ["--temp-dir", str(self.storage)]
                cmd += (
                    ["--rule", json.dumps(self.rule)]
                    if batch
                    else ["--determinant", "a", "--dependent", "b"]
                )
                result = subprocess.run(cmd, check=False, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"regular file", result.stderr)
                self.assertEqual(list(self.storage.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX special files")
    def test_character_device_and_socket_fail_without_read(self):
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        target = self.root / "socket"
        sock.bind(str(target))
        for path in (Path("/dev/null"), target):
            for run in self.runs(path):
                with self.assertRaises(AuditError):
                    run()
                self.assertEqual(list(self.storage.iterdir()), [])

    def test_descriptor_check_not_path_metadata(self):
        real_fstat = os.fstat

        def changed(fd):
            data = real_fstat(fd)
            values = list(data)
            values[0] = stat.S_IFIFO | 0o600
            return os.stat_result(values)

        with (
            patch("depwitness.core.os.fstat", side_effect=changed),
            self.assertRaisesRegex(AuditError, "regular file"),
            _open_regular(self.path),
        ):
            self.fail("nonregular descriptor admitted")

    def test_fdopen_failure_closes_raw_descriptor(self):
        real_close = os.close
        closed = []

        def close(fd):
            closed.append(fd)
            return real_close(fd)

        with (
            patch("depwitness.core.os.fdopen", side_effect=OSError("fdopen failed")),
            patch("depwitness.core.os.close", side_effect=close),
            self.assertRaisesRegex(OSError, "fdopen failed"),
            _open_regular(self.path),
        ):
            self.fail("fdopen failure admitted")
        self.assertEqual(len(closed), 1)
        with self.assertRaises(OSError):
            os.fstat(closed[0])

    def test_fstat_failure_closes_stream(self):
        real_fdopen = os.fdopen
        opened = []

        def fdopen(*args, **kwargs):
            stream = real_fdopen(*args, **kwargs)
            opened.append(stream)
            return stream

        with (
            patch("depwitness.core.os.fdopen", side_effect=fdopen),
            patch("depwitness.core.os.fstat", side_effect=OSError("fstat failed")),
            self.assertRaisesRegex(AuditError, "unreadable"),
        ):
            audit(self.path, **self.rule)
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)

    def test_regular_open_without_nonblock_flag(self):
        real_open = os.open
        flags_seen = []

        def opened(path, flags):
            flags_seen.append(flags)
            return real_open(path, flags)

        with (
            patch("depwitness.core.os.O_NONBLOCK", 0, create=True),
            patch("depwitness.core.os.open", side_effect=opened),
        ):
            report = audit(self.path, **self.rule)
        self.assertFalse(report["passed"])
        self.assertEqual(flags_seen, [os.O_RDONLY | getattr(os, "O_BINARY", 0)])
