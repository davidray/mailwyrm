import unittest

from mailwyrm.daily import render_daily_preview, render_daily_status
from mailwyrm.models import (
    ClassificationRecord,
    DigestAuditEvent,
    LabelAuditEvent,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState


def message(
    message_id: str,
    subject: str,
    *,
    label_ids: list[str] | None = None,
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=label_ids if label_ids is not None else ["INBOX"],
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

    def test_daily_status_summarizes_local_audit_state(self) -> None:
        state = MailwyrmState(
            account_email="user@example.com",
            last_sync_mailbox="inbox",
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
            label_audit_events=[
                label_event(
                    "msg-1",
                    action="add_digested_label",
                    label_names=["Mailwyrm/Digested"],
                ),
                label_event(
                    "msg-1",
                    action="archive_after_digest",
                    label_names=["INBOX"],
                ),
                label_event(
                    "msg-1",
                    action="trash_after_digest",
                    label_names=["TRASH"],
                ),
                label_event(
                    "msg-1",
                    action="restore_trash",
                    label_names=["TRASH", "INBOX"],
                ),
            ],
        )

        status = render_daily_status(state, mailbox="inbox")

        self.assertIn("# Mailwyrm Daily Status", status)
        self.assertIn("Account: user@example.com", status)
        self.assertIn("Last sync mailbox: inbox", status)
        self.assertIn("Indexed messages: 1", status)
        self.assertIn("Digest audit events: 1", status)
        self.assertIn("Unique digested messages: 1", status)
        self.assertIn("Last digest date: 2026-05-25", status)
        self.assertIn("Digested label events: 1", status)
        self.assertIn("Archive events: 1", status)
        self.assertIn("Trash events: 1", status)
        self.assertIn("Restore trash events: 1", status)
        self.assertIn("Archive after digest: 1", status)
        self.assertIn("Archive candidates not yet digested: 0", status)
        self.assertIn("- 2026-05-25: 1", status)
        self.assertIn("- add_digested_label: 1", status)

    def test_daily_status_counts_archive_candidates_not_yet_digested(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Receipt")},
            classifications={"msg-1": classification("msg-1")},
        )

        status = render_daily_status(state)

        self.assertIn("Archive after digest: 1", status)
        self.assertIn("Archive candidates not yet digested: 1", status)

    def test_daily_status_skip_count_excludes_already_archived_all_mail(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Inbox receipt"),
                "msg-2": message("msg-2", "Archived receipt", label_ids=[]),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
        )

        status = render_daily_status(state, mailbox="all-mail")

        self.assertIn("Archive after digest: 2", status)
        self.assertIn("Archive candidates not yet digested: 1", status)

    def test_daily_status_handles_empty_state(self) -> None:
        status = render_daily_status(MailwyrmState())

        self.assertIn("Account: unknown", status)
        self.assertIn("Last digest date: unknown", status)
        self.assertIn("No digest audit events yet.", status)
        self.assertIn("No Gmail mutation audit events yet.", status)


def label_event(
    message_id: str,
    *,
    action: str,
    label_names: list[str],
) -> LabelAuditEvent:
    return LabelAuditEvent(
        message_id=message_id,
        action=action,
        label_names=label_names,
        label_ids=label_names,
        reason="Automated receipt.",
        classifier_version="rules-v0",
        created_at="2026-05-25T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
