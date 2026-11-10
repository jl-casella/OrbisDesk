"""Execute the workflow's real metadata gate without accessing GitHub or PR code."""
import json
import os
from pathlib import Path
import subprocess
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/main-promotion.yml'


@unittest.skipUnless(os.name == 'posix', 'Hosted policy runs in Bash')
class MainPromotionTests(unittest.TestCase):
    def gate(self, **changes):
        # This workflow has one inline step; execute its actual shell body.
        shell = textwrap.dedent(WORKFLOW.read_text().split('        run: |\n', 1)[1])
        env = dict(os.environ, HEAD_REPO='jl-casella/OrbisDesk',
                   GITHUB_REPOSITORY='jl-casella/OrbisDesk', GITHUB_HEAD_REF='dev')
        env.update(changes)
        return subprocess.run(['bash', '-e', '-c', shell], env=env,
                              capture_output=True, text=True)

    def test_same_repository_dev_passes(self):
        self.assertEqual(self.gate().returncode, 0)

    def test_feature_main_and_missing_branch_fail(self):
        for branch in ('feature/change', 'main', '', 'Dev'):
            with self.subTest(branch=branch):
                result = self.gate(GITHUB_HEAD_REF=branch)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('::error::', result.stdout)

    def test_fork_named_dev_and_missing_repository_fail(self):
        for repository in ('contributor/OrbisDesk', ''):
            with self.subTest(repository=repository):
                self.assertNotEqual(self.gate(HEAD_REPO=repository).returncode, 0)

    def test_metadata_is_not_interpreted_as_shell(self):
        self.assertNotEqual(self.gate(HEAD_REPO='$(exit 0)').returncode, 0)
        self.assertNotEqual(self.gate(GITHUB_HEAD_REF='dev" || true #').returncode, 0)

    def test_trusted_workflow_has_no_checkout_or_privileged_steps(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('  pull_request_target:\n    branches: [main]', workflow)
        self.assertIn('permissions: {}', workflow)
        self.assertNotIn('uses:', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('\n    if:', workflow)  # Skipping the job must not accept an invalid PR.
        for event in ('opened', 'reopened', 'synchronize', 'edited', 'ready_for_review'):
            self.assertIn(event, workflow)


class IssueTemplateTests(unittest.TestCase):
    def test_title_prefixes_do_not_contain_literal_quotes(self):
        for filename, expected in (('bug_report.md', '[Bug] '),
                                   ('feature_request.md', '[Feature] ')):
            with self.subTest(template=filename):
                template = (ROOT / '.github/ISSUE_TEMPLATE' / filename).read_text()
                frontmatter = template.split('---', 2)[1]
                title = next(line.partition(':')[2].strip()
                             for line in frontmatter.splitlines() if line.startswith('title:'))
                self.assertEqual(json.loads(title), expected)
