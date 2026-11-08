"""Failure-path tests for contract evaluation, not emulator substitutes."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('matrix', Path(__file__).with_name('run-matrix.py'))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class ContractTests(unittest.TestCase):
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

    def test_service_assertion_cannot_be_skipped_or_duplicated(self):
        case = {'kind': 'services', 'case': 'ipc', 'assertions': ['scm-rights']}
        record = 'PWSERVICE {"case":"scm-rights","status":"passed"}\n'
        end = 'PWCI {"case":"ipc","exit_code":0}\n'
        self.assertEqual(matrix.evaluate(case, record + end, 0, False), [])
        self.assertTrue(matrix.evaluate(case, end, 0, False))
        self.assertTrue(matrix.evaluate(case, record + record + end, 0, False))


if __name__ == '__main__':
    unittest.main()
