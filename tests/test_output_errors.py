"""Output failures must produce exit2, not an uncaught exception/exit1."""

import errno
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depwitness.__main__ import main


class FailingOutput(io.StringIO):
    def __init__(self, phase, number):
        super().__init__()
        self.phase, self.number = phase, number

    def write(self, text):
        if self.phase == "write":
            raise OSError(self.number, "simulated output failure")
        return super().write(text)

    def flush(self):
        if self.phase == "flush":
            raise OSError(self.number, "simulated output failure")
        return super().flush()


class OutputErrorsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input.csv"
        self.path.write_text("k,v\na,x\na,y\n", encoding="utf-8")
        self.args = [str(self.path), "--determinant", "k", "--dependent", "v"]

    def test_stdout_write_and_flush_io_errors_exit2(self):
        for phase in ("write", "flush"):
            for number in (errno.ENOSPC, errno.EIO, errno.EBADF):
                with self.subTest(phase=phase, number=number):
                    sink = FailingOutput(phase, number)
                    with patch("depwitness.__main__.sys.stdout", sink):
                        self.assertEqual(main(self.args), 2)
                    if phase == "write":
                        self.assertEqual(sink.getvalue(), "")

    def test_stderr_failure_during_invalid_input_still_exit2(self):
        self.path.unlink()
        out = io.StringIO()
        with (
            patch("depwitness.__main__.sys.stdout", out),
            patch("depwitness.__main__.sys.stderr", FailingOutput("write", errno.ENOSPC)),
        ):
            self.assertEqual(main(self.args), 2)
        self.assertEqual(out.getvalue(), "")

    def test_batch_output_error_and_broken_pipe_exit2(self):
        args = [str(self.path), "--rule", '{"determinant":["k"],"dependent":["v"]}']
        for number in (errno.EPIPE, errno.ENOSPC):
            with (
                self.subTest(number=number),
                patch("depwitness.__main__.sys.stdout", FailingOutput("write", number)),
            ):
                self.assertEqual(main(args), 2)

    @unittest.skipUnless(Path("/dev/full").exists(), "requires a real full output device")
    def test_real_full_device_exit2_without_shutdown_override(self):
        import os
        import subprocess
        import sys

        env = dict(os.environ)
        env["PYTHONPATH"] = (
            str(Path(__file__).resolve().parents[1] / "src")
            + os.pathsep
            + env.get("PYTHONPATH", "")
        )
        command = [sys.executable, "-m", "depwitness", *self.args]
        with open("/dev/full", "wb", buffering=0) as sink:
            result = subprocess.run(
                command, stdout=sink, stderr=subprocess.PIPE, env=env, check=False
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertNotIn(b"Exception ignored", result.stderr)
        self.path.unlink()
        with open("/dev/full", "wb", buffering=0) as sink:
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=sink, env=env, check=False
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")

    def test_main_does_not_close_caller_owned_stream(self):
        sink = FailingOutput("write", errno.ENOSPC)
        with patch("depwitness.__main__.sys.stdout", sink):
            self.assertEqual(main(self.args), 2)
        self.assertFalse(sink.closed)

    @unittest.skipUnless(Path("/dev/full").exists(), "requires a real full output device")
    def test_argparse_full_devices_return_exit2(self):
        import os
        import subprocess
        import sys

        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        for args, channel in ((["--help"], "stdout"), (["--not-an-option"], "stderr")):
            with self.subTest(args=args), open("/dev/full", "wb", buffering=0) as full:
                streams = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
                streams[channel] = full
                result = subprocess.run(
                    [sys.executable, "-m", "depwitness", *args], env=env, check=False, **streams
                )
            self.assertEqual(result.returncode, 2, result)
            if result.stderr is not None:
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertNotIn(b"Exception ignored", result.stderr)

    def test_argparse_normal_exit_codes_are_preserved(self):
        from depwitness.__main__ import cli

        for args, expected in ((["--help"], 0), (["--not-an-option"], 2)):
            with (
                self.subTest(args=args),
                patch("sys.argv", ["depwitness", *args]),
                patch("sys.stdout", io.StringIO()),
                patch("sys.stderr", io.StringIO()),
            ):
                self.assertEqual(cli(), expected)
