"""Exercise actual shell build trailers; fake Ninja tests control flow, not Mesa."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'posix', 'Zink build scripts run in Bash')
class ZinkBuildStatusTests(unittest.TestCase):
    def test_clean_build_and_compiler_failure_keep_their_status_and_logs(self):
        scripts = Path(__file__).resolve().parents[1] / 'vk-h0'
        for name in ('build-mesa-zink.sh', 'build-mesa-zink-i386.sh'):
            source = (scripts / name).read_text()
            trailer = source[source.index('ninja -C $build '):]
            for code in (0, 17):
                with self.subTest(script=name, exit_code=code), tempfile.TemporaryDirectory() as directory:
                    build = Path(directory) / 'build'
                    for relative in ('src/gallium/targets/libgl-gdi/opengl32.dll',
                                     'src/gallium/targets/wgl/libgallium_wgl.dll'):
                        path = build / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('Test fixture only, not a DLL')
                    shell = ('set -euo pipefail\n'
                             'build="$TEST_BUILD"\n'
                             'ninja() { printf "controlled Ninja output\\n"; return "$TEST_EXIT"; }\n' + trailer)
                    result = subprocess.run(['bash', '-c', shell], capture_output=True, text=True,
                                            env=dict(os.environ, TEST_BUILD=str(build), TEST_EXIT=str(code)))
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertIn('controlled Ninja output', result.stdout)
                    self.assertIn('controlled Ninja output', Path(str(build) + '.log').read_text())


if __name__ == '__main__':
    unittest.main()
