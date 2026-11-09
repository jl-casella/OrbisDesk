"""Execute the actual product authorization gate without building or publishing."""
import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.name == 'posix', 'The hosted product gate runs in Bash')
class ProductAuthorizationTests(unittest.TestCase):
    def gate(self, **changes):
        env = dict(os.environ, EVENT='workflow_dispatch', ACTOR='owner',
                   TRIGGERING_ACTOR='owner', OWNER='owner', AUTO_ENABLED='',
                   PUBLISH_REQUESTED='false', GITHUB_REF='refs/heads/ci/release-fix')
        env.update(changes)
        return subprocess.run(['bash', str(Path(__file__).with_name('authorize-product.sh'))],
                              env=env, capture_output=True).returncode

    def test_owner_can_build_branch_without_publication(self):
        self.assertEqual(self.gate(), 0)
        self.assertEqual(self.gate(GITHUB_REF='refs/heads/main'), 0)

    def test_publication_requires_main(self):
        self.assertNotEqual(self.gate(PUBLISH_REQUESTED='true'), 0)
        self.assertEqual(self.gate(PUBLISH_REQUESTED='true', GITHUB_REF='refs/heads/main'), 0)

    def test_manual_actor_and_rerun_actor_must_be_owner(self):
        self.assertNotEqual(self.gate(ACTOR='writer'), 0)
        self.assertNotEqual(self.gate(TRIGGERING_ACTOR='writer'), 0)

    def test_automatic_runs_require_enabled_main_push(self):
        self.assertNotEqual(self.gate(EVENT='push', GITHUB_REF='refs/heads/main'), 0)
        self.assertNotEqual(self.gate(EVENT='push', AUTO_ENABLED='true'), 0)
        self.assertEqual(self.gate(EVENT='push', GITHUB_REF='refs/heads/main', AUTO_ENABLED='true'), 0)

    def test_tags_unexpected_events_and_invalid_inputs_are_rejected(self):
        self.assertNotEqual(self.gate(GITHUB_REF='refs/tags/test'), 0)
        self.assertNotEqual(self.gate(EVENT='pull_request'), 0)
        self.assertNotEqual(self.gate(PUBLISH_REQUESTED='invalid'), 0)


if __name__ == '__main__':
    unittest.main()
