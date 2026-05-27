import unittest

from mailwyrm.digest import (
    build_digest_bundles,
    mark_digest_items,
    message_has_been_digested,
    render_digest,
)
from mailwyrm.models import (
    ClassificationCorrection,
    ClassificationRecord,
    MessageRecord,
)
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


def message_with_body(message_id: str, subject: str, body_text: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="A short useful snippet.",
        headers={"From": "Alerts <no-reply@example.com>", "Subject": subject},
        body_text=body_text,
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


def classification_correction(
    message_id: str,
    *,
    category: str,
    machine_type: str | None,
) -> ClassificationCorrection:
    return ClassificationCorrection(
        message_id=message_id,
        category=category,
        machine_type=machine_type,
        reason="User correction.",
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

    def test_build_digest_bundles_groups_machine_messages_by_type(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Top story"),
                "msg-2": message("msg-2", "Flash sale"),
                "msg-3": message("msg-3", "Second story"),
            },
            classifications={
                "msg-1": classification("msg-1", category="machine", machine_type="news"),
                "msg-2": classification(
                    "msg-2",
                    category="machine",
                    machine_type="marketing",
                ),
                "msg-3": classification("msg-3", category="machine", machine_type="news"),
            },
        )

        bundles = build_digest_bundles(state)

        news = next(bundle for bundle in bundles if bundle.machine_type == "news")
        self.assertEqual(news.title, "News")
        self.assertEqual(news.message_ids, ["msg-1", "msg-3"])
        self.assertEqual(news.count, 2)

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

    def test_digest_uses_corrected_classification(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Weekly update")},
            classifications={
                "msg-1": classification("msg-1", category="human", machine_type=None)
            },
        )
        state.corrections["msg-1"] = classification_correction(
            "msg-1",
            category="machine",
            machine_type="newsletter",
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("## Newsletters", digest)
        self.assertIn("Weekly update", digest)

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

    def test_digest_uses_body_text_when_available(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message_with_body(
                    "msg-1",
                    "Delivery update",
                    "Package arrives Friday by 8 PM.",
                )
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="delivery",
                )
            },
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("Body: Package arrives Friday by 8 PM.", digest)
        self.assertNotIn("Snippet: A short useful snippet.", digest)

    def test_digest_can_limit_items(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "First receipt"),
                "msg-2": message("msg-2", "Second receipt"),
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                ),
                "msg-2": classification(
                    "msg-2",
                    category="machine",
                    machine_type="transactional",
                ),
            },
        )

        digest = render_digest(state, title_date="2026-05-25", limit=1)

        self.assertIn("Items: 1", digest)
        self.assertIn("First receipt", digest)
        self.assertNotIn("Second receipt", digest)

    def test_digest_zero_limit_reports_hidden_items(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "First receipt")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                )
            },
        )

        digest = render_digest(state, title_date="2026-05-25", limit=0)

        self.assertIn("Items: 0", digest)
        self.assertIn("No digest items are shown because the limit is 0.", digest)
        self.assertNotIn("First receipt", digest)

    def test_digest_rejects_negative_limit(self) -> None:
        with self.assertRaises(ValueError):
            render_digest(MailwyrmState(), title_date="2026-05-25", limit=-1)

    def test_digest_escapes_markdown_from_email_content(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-msg-1",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["INBOX"],
                    snippet="Click ](https://bad.example) *now*",
                    headers={
                        "From": "Sender ](https://bad.example)",
                        "Subject": "Receipt ](https://bad.example)",
                    },
                )
            },
            classifications={
                "msg-1": ClassificationRecord(
                    message_id="msg-1",
                    category="machine",
                    machine_type="transactional",
                    importance="medium",
                    automation_safety="medium",
                    confidence=0.82,
                    reason="Reason ](https://bad.example)",
                    suggested_actions=["digest"],
                    classifier_version="rules-v0",
                )
            },
        )

        digest = render_digest(state, title_date="2026-05-25")

        self.assertIn("Receipt \\]\\(https://bad.example\\)", digest)
        self.assertIn("Sender \\]\\(https://bad.example\\)", digest)
        self.assertIn("Reason \\]\\(https://bad.example\\)", digest)
        self.assertIn("Click \\]\\(https://bad.example\\) \\*now\\*", digest)

    def test_mark_digest_items_records_included_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "Your receipt"),
                "msg-2": message("msg-2", "Re: dinner"),
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                ),
                "msg-2": classification("msg-2", category="human", machine_type=None),
            },
        )

        marked = mark_digest_items(state, title_date="2026-05-25")

        self.assertEqual(marked, 1)
        self.assertTrue(message_has_been_digested(state, "msg-1"))
        self.assertFalse(message_has_been_digested(state, "msg-2"))
        self.assertEqual(state.digest_audit_events[0].message_id, "msg-1")
        self.assertEqual(
            state.digest_audit_events[0].reason,
            "Automated sender or subject pattern.",
        )

    def test_mark_digest_items_is_idempotent_for_same_digest_date(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Your receipt")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                )
            },
        )

        first_marked = mark_digest_items(state, title_date="2026-05-25")
        second_marked = mark_digest_items(state, title_date="2026-05-25")

        self.assertEqual(first_marked, 1)
        self.assertEqual(second_marked, 0)
        self.assertEqual(len(state.digest_audit_events), 1)


if __name__ == "__main__":
    unittest.main()
