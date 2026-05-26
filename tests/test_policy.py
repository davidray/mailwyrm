import unittest

from mailwyrm.models import AutomationPolicy
from mailwyrm.policy import render_policy_status


class PolicyTest(unittest.TestCase):
    def test_policy_status_shows_conservative_defaults(self) -> None:
        status = render_policy_status(AutomationPolicy())

        self.assertIn("# Mailwyrm Policy Status", status)
        self.assertIn("Archive after digest: enabled", status)
        self.assertIn("Trash after digest: disabled", status)
        self.assertIn("Trash automation is disabled.", status)

    def test_policy_status_shows_trash_opt_in(self) -> None:
        status = render_policy_status(
            AutomationPolicy(trash_after_digest_enabled=True)
        )

        self.assertIn("Trash after digest: enabled", status)
        self.assertIn("Trash automation is enabled in local policy.", status)

    def test_policy_parses_hand_edited_false_string(self) -> None:
        policy = AutomationPolicy.from_dict(
            {
                "archive_after_digest_enabled": "false",
                "trash_after_digest_enabled": "false",
            }
        )

        self.assertFalse(policy.archive_after_digest_enabled)
        self.assertFalse(policy.trash_after_digest_enabled)

    def test_policy_defaults_when_local_state_value_is_not_an_object(self) -> None:
        policy = AutomationPolicy.from_dict(None)

        self.assertTrue(policy.archive_after_digest_enabled)
        self.assertFalse(policy.trash_after_digest_enabled)


if __name__ == "__main__":
    unittest.main()
