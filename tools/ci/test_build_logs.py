"""A failed nested builder must expose its real error and retain its exit status."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from common import run


class BuildLogTests(unittest.TestCase):
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
