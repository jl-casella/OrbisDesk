"""Failure-path tests for contract evaluation, not emulator substitutes."""
import importlib.util
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch
import common

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('matrix', Path(__file__).with_name('run-matrix.py'))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class ContractTests(unittest.TestCase):
    def test_private_profile_preserves_internal_logs_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'
            work.mkdir()
            output = Path(directory) / 'evidence'
            env = matrix.prepare_user_environment(work)
            user = Path(env['XDG_DATA_HOME']) / 'shadPS4'
            self.assertTrue((user / 'home/1000/savedata').is_dir())
            self.assertFalse((user / 'users.json').exists())
            (user / 'log').mkdir()
            (user / 'log/shad_log.txt').write_text('Failed to initialize SDL video subsystem')
            (user / 'config.json').write_text('{}')
            external = Path(directory) / 'external.txt'
            external.write_text('Must not be captured')
            (user / 'log/external.log').symlink_to(external)
            matrix.collect_emulator_evidence(work, output)
            self.assertIn('SDL video', (output / 'emulator-user/log/shad_log.txt').read_text())
            self.assertFalse((output / 'emulator-user/log/external.log').exists())
            self.assertEqual(len(json.loads((output / 'emulator-evidence.json').read_text())['files']), 2)

    def test_startup_abort_keeps_unexecuted_cases_pending(self):
        for guest_marker in (False, True):
            with self.subTest(guest_marker=guest_marker), tempfile.TemporaryDirectory() as directory:
                report = {'cases': [], 'contract_passed': False, 'complete_profile': False}
                cases = [dict(id='first', case='console32', emulator='fork', timeout_seconds=60),
                         dict(id='second', case='console32', emulator='official', timeout_seconds=60),
                         dict(id='third', case='files', emulator='fork', timeout_seconds=60)]
                results = [dict(id=c['id'], timed_out=True, guest_marker_seen=guest_marker,
                                outcome_as_expected=False) for c in cases]
                with patch.object(matrix, 'RESULTS', Path(directory)), patch.object(common, 'RESULTS', Path(directory)), \
                        patch.object(matrix, 'execute', side_effect=results) as execute:
                    matrix.execute_cases(cases, report, {}, {}, {}, stop_on_startup_failure=True)
                self.assertFalse(report['contract_passed'])
                self.assertEqual(execute.call_count, 3 if guest_marker else 2)
                self.assertEqual(report['pending_cases'], [] if guest_marker else ['third'])
                self.assertEqual(report['execution_completed'], guest_marker)

    def test_interrupted_run_keeps_checkpoint_and_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = {'cases': [], 'contract_passed': False, 'complete_profile': False}
            cases = [{'id': name, 'timeout_seconds': 60} for name in ('first', 'interrupted')]
            result = {'id': 'first', 'outcome_as_expected': True}
            with patch.object(matrix, 'RESULTS', Path(directory)), patch.object(common, 'RESULTS', Path(directory)), \
                    patch.object(matrix, 'execute', side_effect=[result, KeyboardInterrupt]), \
                    self.assertRaises(KeyboardInterrupt):
                matrix.execute_cases(cases, report, {}, {}, {})
            saved = json.loads((Path(directory) / 'matrix-report.json').read_text())
            self.assertEqual(saved['cases'], [result])
            self.assertEqual(saved['active_case'], 'interrupted')
            self.assertEqual(saved['pending_cases'], ['interrupted'])
            self.assertFalse(saved['contract_passed'])
            self.assertFalse(saved['execution_completed'])
            self.assertFalse(saved['complete_profile'])

    def setUp(self):
        self.case = {'kind': 'baseline', 'case': 'files', 'expected': 'passed', 'exit_code': 0}
        self.text = 'PWPS4 {"event":"start","case":"files","status":"running","code":0}\n' + \
                    'PWPS4 {"event":"result","case":"files","status":"passed","code":0}\n'

    def test_real_success_requires_both_events_and_exit(self):
        self.assertEqual(matrix.evaluate(self.case, self.text, 0, False), [])
        self.assertTrue(matrix.evaluate(self.case, self.text, 1, False))
        self.assertTrue(matrix.evaluate(self.case, self.text, 0, True))
        self.assertTrue(matrix.evaluate(self.case, '', 0, False))

    def test_timeout_is_not_an_expected_official_blocker_by_itself(self):
        case = dict(self.case, expected='blocked', blocker='specific exit assertion')
        self.assertTrue(matrix.evaluate(case, self.text, -9, True))
        self.assertEqual(matrix.evaluate(case, self.text + 'specific exit assertion', -9, True), [])
        self.assertTrue(matrix.evaluate(case, 'specific exit assertion', -9, True))

    def test_wrong_reference_is_never_a_pass(self):
        self.assertIn('windows-reference-output-differs', matrix.evaluate(self.case, self.text, 0, False, False))

    def test_official_trap_requires_exact_signature_guest_and_reference(self):
        case = dict(self.case, expected='blocked', blocker='process.cpp:312 exit: Unreachable code!',
                    blocker_exit_codes=[-5])
        text = self.text + case['blocker']
        self.assertEqual(matrix.evaluate(case, text, -5, False), [])
        self.assertTrue(matrix.evaluate(case, self.text, -5, False))
        self.assertTrue(matrix.evaluate(case, case['blocker'], -5, False))
        self.assertTrue(matrix.evaluate(case, text, -5, False, False))
        for code in (0, 1, -11, -6, -9):
            self.assertTrue(matrix.evaluate(case, text, code, False))
        self.assertTrue(matrix.evaluate(self.case, text, -5, False))

    def test_service_assertion_cannot_be_skipped_or_duplicated(self):
        case = {'kind': 'services', 'case': 'ipc', 'assertions': ['scm-rights']}
        record = 'PWSERVICE {"case":"scm-rights","status":"passed"}\n'
        end = 'PWCI {"case":"ipc","exit_code":0}\n'
        self.assertEqual(matrix.evaluate(case, record + end, 0, False), [])
        self.assertTrue(matrix.evaluate(case, end, 0, False))
        self.assertTrue(matrix.evaluate(case, record + record + end, 0, False))


if __name__ == '__main__':
    unittest.main()
