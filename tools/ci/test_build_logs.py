"""A failed nested builder must expose its real error and retain its exit status."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from common import run


class BuildLogTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Process group cleanup is POSIX-specific')
    def test_timeout_stops_driver_and_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            pidfile = directory / 'child.pid'
            child = ('import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); '
                     'print("real descendant started", flush=True); time.sleep(60)')
            driver = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); '
                      'time.sleep(60)')
            with redirect_stdout(io.StringIO()), self.assertRaises(subprocess.TimeoutExpired):
                run([sys.executable, '-c', driver, child, pidfile], directory / 'timeout.log', timeout=2)
            pid = int(pidfile.read_text())
            state = Path('/proc') / str(pid) / 'stat'
            if state.exists():
                # A reparented zombie is dead and cannot keep compiling/writing ccache.
                self.assertEqual(state.read_text().rsplit(')', 1)[1].split()[0], 'Z')
            self.assertIn('real descendant started', (directory / 'timeout.log').read_text())

    def test_nested_failure_reaches_actions_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            inner = directory / 'configure.log'
            outer = directory / 'driver.log'
            # Exercise both real capture layers, without replacing the emulator result.
            script = ('import sys; sys.path.insert(0, sys.argv[1]); '
                      'from logged_process import run_logged; '
                      'run_logged([sys.executable,"-c",'
                      '"import sys; print(\'CMake Error: required test dependency missing\', file=sys.stderr); sys.exit(17)"],sys.argv[2])')
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(subprocess.CalledProcessError) as failure:
                run([sys.executable, '-c', script, Path(__file__).resolve().parents[1], inner], outer)
            self.assertNotEqual(failure.exception.returncode, 0)
            self.assertIn('CMake Error: required test dependency missing', output.getvalue())
            self.assertIn('CMake Error: required test dependency missing', inner.read_text())
            self.assertIn('CMake Error: required test dependency missing', outer.read_text())

    def test_original_child_exit_status_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError) as failure:
                run([sys.executable, '-c', 'raise SystemExit(17)'], Path(directory) / 'failure.log')
            self.assertEqual(failure.exception.returncode, 17)


if __name__ == '__main__':
    unittest.main()
