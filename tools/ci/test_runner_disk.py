"""Hosted cleanup boundaries and real process termination without filling a disk."""
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import runner_disk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import logged_process

spec = importlib.util.spec_from_file_location('build_wine',
    Path(__file__).resolve().parents[1] / 'build-wine.py')
build_wine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_wine)


class RunnerDiskTests(unittest.TestCase):
    def test_cleanup_refuses_workstations_and_self_hosted_runners(self):
        for env in ({}, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted'}):
            with patch.dict(os.environ, env, clear=True), patch.object(runner_disk.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    runner_disk.prepare()
                run.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'Hosted cleanup is Linux only')
    def test_cleanup_only_removes_allowlisted_unused_tools(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted'}), \
                patch.object(Path, 'is_symlink', return_value=False), \
                patch.object(Path, 'exists', return_value=True), \
                patch.object(runner_disk, 'record'), patch.object(runner_disk.subprocess, 'run') as run:
            runner_disk.prepare()
            self.assertEqual([call.args[0] for call in run.call_args_list],
                [['sudo', 'rm', '-rf', '--', name] for name in runner_disk.UNUSED_RUNNER_TREES] +
                [['sudo', 'apt-get', 'clean']])
            for name in runner_disk.UNUSED_RUNNER_TREES:
                self.assertNotIn('dotnet', name)
                self.assertNotIn('python', name.lower())
                self.assertFalse(Path(name).is_relative_to(runner_disk.ROOT))

    def test_release_flags_cover_native_and_both_pe_architectures(self):
        with patch.dict(os.environ, {'CFLAGS': '-O0 -g', 'i386_CXXFLAGS': '-g'}):
            self.assertEqual(build_wine.build_environment()['CFLAGS'], '-O0 -g')
            release = build_wine.build_environment(True)
            for key in ('CFLAGS', 'CXXFLAGS', 'CROSSCFLAGS', 'i386_CFLAGS',
                        'i386_CXXFLAGS', 'x86_64_CFLAGS', 'x86_64_CXXFLAGS'):
                self.assertEqual(release[key], '-O2 -g0')

    def test_compiler_omits_dwarf_with_release_flags_after_wine_debug_format_flag(self):
        compilers = [(cc, key) for cc, key in (('gcc', 'CFLAGS'),
                     ('i686-w64-mingw32-gcc', 'i386_CFLAGS'),
                     ('x86_64-w64-mingw32-gcc', 'x86_64_CFLAGS')) if shutil.which(cc)]
        if not compilers or not shutil.which('objdump'):
            self.skipTest('Requires a host/PE compiler and objdump')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sample.c'
            source.write_text('int sample(int value) { return value * 7 + 3; }\n')
            for compiler, key in compilers:
                with self.subTest(compiler=compiler):
                    for mode, flags in (('debug', '-g -O2'),
                                        ('release', build_wine.build_environment(True)[key])):
                        obj = Path(directory) / (compiler + '-' + mode + '.o')
                        subprocess.run([compiler, '-c', '-gdwarf-4', *shlex.split(flags),
                                        str(source), '-o', str(obj)], check=True, capture_output=True)
                        sections = subprocess.check_output(['objdump', '-h', str(obj)], text=True)
                        self.assertEqual('.debug_info' in sections, mode == 'debug')

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_low_disk_terminates_and_reaps_running_build(self):
        real_popen = subprocess.Popen
        processes = []
        def start(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(logged_process.subprocess, 'Popen', side_effect=start), \
                patch.object(logged_process.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(OSError, 'disk reserve exhausted'):
                logged_process.run_logged([sys.executable, '-c', 'import time; time.sleep(30)'],
                    Path(directory) / 'build.log', cwd=directory,
                    timeout=60, process_group=True, minimum_free_bytes=1024)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_disk_monitor_keeps_timeout_enforcement(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(logged_process.shutil, 'disk_usage', return_value=SimpleNamespace(free=4096)):
            with self.assertRaises(subprocess.TimeoutExpired):
                logged_process.run_logged([sys.executable, '-c', 'import time; time.sleep(30)'],
                    Path(directory) / 'build.log', timeout=0.1,
                    process_group=True, minimum_free_bytes=1024)
