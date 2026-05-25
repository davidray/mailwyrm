import unittest

from mailwyrm.digest import render_digest
from mailwyrm.models import ClassificationRecord, MessageRecord
from mailwyrm.store import MailwyrmState


def message(message_id: str, subject: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="A short useful snippet.",
        headers={"From": "Alerts <no-reply@example.com>", "Subject": subject},
    )


def classification(
    message_id: str,
    *,
    category: str,
    machine_type: str | None,
    importance: str = "medium",
) -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category=category,
        machine_type=machine_type,
        importance=importance,
        automation_safety="medium" if category == "machine" else "low",
        confidence=0.82,
        reason="Automated sender or subject pattern.",
        suggested_actions=["digest"],
        classifier_version="rules-v0",
    )


class DigestTest(unittest.TestCase):
    def test_digest_groups_machine_messages_and_links_to_gmail(self) -> None:
        state = MailwyrmState(
            account_email="user@example.com",
            messages={
                "msg-1": message("msg-1", "Your receipt"),
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                )
            },
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("# Mailwyrm Machine Digest - 2026-05-25", digest)
        self.assertIn("## Transactional", digest)
        self.assertIn("[Your receipt](https://mail.google.com/mail/u/0/#inbox/msg-1)", digest)

    def test_digest_excludes_human_messages(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Re: dinner")},
            classifications={
                "msg-1": classification("msg-1", category="human", machine_type=None)
            },
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("Items: 0", digest)
        self.assertNotIn("Re: dinner", digest)

    def test_digest_includes_high_importance_review_items(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Security alert")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="needs_review",
                    machine_type="security",
                    importance="high",
                )
            },
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("## Needs Review", digest)
        self.assertIn("Security alert", digest)


if __name__ == "__main__":
    unittest.main()
