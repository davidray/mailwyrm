import unittest

from mailwyrm.daily import render_daily_preview
from mailwyrm.models import ClassificationRecord, DigestAuditEvent, MessageRecord
from mailwyrm.store import MailwyrmState


def message(message_id: str, subject: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="Snippet",
        headers={"Subject": subject},
    )


def classification(message_id: str) -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category="machine",
        machine_type="transactional",
        importance="medium",
        automation_safety="medium",
        confidence=0.86,
        reason="Automated receipt.",
        suggested_actions=["digest"],
        classifier_version="rules-v0",
    )


def digest_event(message_id: str) -> DigestAuditEvent:
    return DigestAuditEvent(
        message_id=message_id,
        digest_title_date="2026-05-25",
        reason="Automated receipt.",
        classifier_version="rules-v0",
        created_at="2026-05-25T00:00:00+00:00",
    )


class DailyPreviewTest(unittest.TestCase):
    def test_daily_preview_combines_digest_labels_and_actions(self) -> None:
        state = MailwyrmState(
            account_email="user@example.com",
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
        )

        preview = render_daily_preview(
            state,
            title_date="2026-05-25",
            limit=10,
            mailbox="inbox",
        )

        self.assertIn("# Mailwyrm Daily Preview - 2026-05-25", preview)
        self.assertIn("## Machine Digest", preview)
        self.assertIn("# Mailwyrm Machine Digest - 2026-05-25", preview)
        self.assertIn("## Gmail Digested Labels", preview)
        self.assertIn("msg-1\tMailwyrm/Digested\tReceipt", preview)
        self.assertIn("## Mailbox Actions", preview)
        self.assertIn("Mailbox scope: inbox", preview)
        self.assertIn("No Gmail actions will be performed.", preview)
        self.assertIn("msg-1\tarchive_after_digest\tmachine\t0.86\tReceipt", preview)

    def test_daily_preview_can_report_pending_gmail_mutation(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
        )

        preview = render_daily_preview(
            state,
            title_date="2026-05-25",
            mutates_gmail=True,
        )

        self.assertIn("Gmail labels and archive state may be changed", preview)
        self.assertIn("Gmail will be modified after this preview.", preview)
        self.assertIn("Trash is not applied.", preview)

    def test_daily_preview_does_not_mark_digest_items(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )

        render_daily_preview(state, title_date="2026-05-25")

        self.assertEqual(state.digest_audit_events, [])


if __name__ == "__main__":
    unittest.main()
