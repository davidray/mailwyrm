import tempfile
import unittest
from pathlib import Path

from mailwyrm.models import (
    AutomationPolicy,
    ClassificationCorrection,
    ClassificationRecord,
    DigestAuditEvent,
    LabelAuditEvent,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState, read_state, write_state


class StoreTest(unittest.TestCase):
    def test_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            state = MailwyrmState(
                account_email="user@example.com",
                history_id="123",
                last_sync_mailbox="all-mail",
                messages={
                    "msg-1": MessageRecord(
                        id="msg-1",
                        thread_id="thread-1",
                        history_id="10",
                        internal_date="1710000000000",
                        label_ids=["INBOX"],
                        snippet="A short snippet",
                        headers={"Subject": "Hello"},
                    )
                },
                classifications={
                    "msg-1": ClassificationRecord(
                        message_id="msg-1",
                        category="human",
                        machine_type=None,
                        importance="medium",
                        automation_safety="low",
                        confidence=0.68,
                        reason="Reply-style subject suggests a human conversation.",
                        suggested_actions=["review"],
                        classifier_version="rules-v0",
                    )
                },
                corrections={
                    "msg-1": ClassificationCorrection(
                        message_id="msg-1",
                        category="machine",
                        machine_type="newsletter",
                        reason="Known newsletter.",
                    )
                },
                digest_audit_events=[
                    DigestAuditEvent(
                        message_id="msg-1",
                        digest_title_date="2026-05-25",
                        reason="Known newsletter.",
                        classifier_version="rules-v0+user-correction",
                        created_at="2026-05-25T00:00:00+00:00",
                    )
                ],
                label_audit_events=[
                    LabelAuditEvent(
                        message_id="msg-1",
                        action="add_labels",
                        label_names=["Mailwyrm/Machine"],
                        label_ids=["Label_1"],
                        reason="Known newsletter.",
                        classifier_version="rules-v0+user-correction",
                        created_at="2026-05-25T00:00:00+00:00",
                    )
                ],
                automation_policy=AutomationPolicy(
                    archive_after_digest_enabled=True,
                    trash_after_digest_enabled=True,
                ),
            )

            write_state(path, state)
            loaded = read_state(path)
            mode = path.stat().st_mode & 0o777

        self.assertEqual(loaded.account_email, "user@example.com")
        self.assertEqual(loaded.history_id, "123")
        self.assertEqual(loaded.last_sync_mailbox, "all-mail")
        self.assertEqual(loaded.messages["msg-1"].headers["Subject"], "Hello")
        self.assertEqual(loaded.classifications["msg-1"].category, "human")
        self.assertEqual(loaded.corrections["msg-1"].machine_type, "newsletter")
        self.assertEqual(loaded.digest_audit_events[0].message_id, "msg-1")
        self.assertEqual(loaded.label_audit_events[0].label_ids, ["Label_1"])
        self.assertTrue(loaded.automation_policy.archive_after_digest_enabled)
        self.assertTrue(loaded.automation_policy.trash_after_digest_enabled)
        self.assertEqual(mode, 0o600)

    def test_state_defaults_to_conservative_automation_policy(self) -> None:
        state = MailwyrmState.from_dict({})

        self.assertTrue(state.automation_policy.archive_after_digest_enabled)
        self.assertFalse(state.automation_policy.trash_after_digest_enabled)


if __name__ == "__main__":
    unittest.main()
