import unittest

from mailwyrm.cockpit import build_daily_cockpit_payload
from mailwyrm.models import (
    AutomationPolicy,
    ClassificationRecord,
    DigestAuditEvent,
    LabelAuditEvent,
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
        snippet="A useful local snippet.",
        headers={"From": "Sender <sender@example.com>", "Subject": subject},
    )


def classification(
    message_id: str,
    *,
    category: str = "machine",
    machine_type: str | None = "notification",
    importance: str = "medium",
    automation_safety: str = "medium",
    confidence: float = 0.86,
    suggested_actions: list[str] | None = None,
) -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category=category,
        machine_type=machine_type,
        importance=importance,
        automation_safety=automation_safety,
        confidence=confidence,
        reason="Automated sender or subject pattern.",
        suggested_actions=suggested_actions if suggested_actions is not None else ["digest"],
        classifier_version="rules-v0",
    )


class CockpitTest(unittest.TestCase):
    def test_build_daily_cockpit_payload_combines_local_views(self) -> None:
        state = MailwyrmState(
            account_email="user@example.com",
            last_sync_mailbox="inbox",
            messages={
                "msg-1": message("msg-1", "Receipt"),
                "msg-2": message("msg-2", "Copilot"),
                "msg-3": message("msg-3", "Dinner"),
                "msg-4": message("msg-4", "Security alert"),
                "msg-5": MessageRecord(
                    id="msg-5",
                    thread_id="thread-msg-5",
                    history_id="10",
                    internal_date="1710000000001",
                    label_ids=["INBOX"],
                    snippet="A useful local snippet.",
                    headers={
                        "From": "Sender <sender@example.com>",
                        "Subject": "Unclassified",
                    },
                ),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification(
                    "msg-2",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                ),
                "msg-3": classification(
                    "msg-3",
                    category="human",
                    machine_type=None,
                    suggested_actions=[],
                ),
                "msg-4": classification(
                    "msg-4",
                    category="needs_review",
                    machine_type="security",
                    importance="high",
                    automation_safety="low",
                    confidence=0.72,
                    suggested_actions=["review", "protect"],
                ),
            },
            digest_audit_events=[
                DigestAuditEvent(
                    message_id="msg-2",
                    digest_title_date="2026-05-25",
                    reason="Low-risk notification.",
                    classifier_version="rules-v0",
                    created_at="2026-05-25T00:00:00+00:00",
                )
            ],
            label_audit_events=[
                LabelAuditEvent(
                    message_id="msg-2",
                    action="trash_after_digest",
                    label_names=["TRASH"],
                    label_ids=["TRASH"],
                    reason="Low-risk notification.",
                    classifier_version="rules-v0",
                    created_at="2026-05-26T00:00:00+00:00",
                )
            ],
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        payload = build_daily_cockpit_payload(
            state,
            title_date="2026-05-26",
            limit=1,
            mailbox="inbox",
            audit_limit=1,
        )

        self.assertEqual(payload["date"], "2026-05-26")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["account"]["email"], "user@example.com")
        self.assertEqual(payload["attention"]["machine"], 2)
        self.assertEqual(payload["lanes"]["human"]["total_items"], 1)
        self.assertEqual(payload["lanes"]["human"]["items"][0]["subject"], "Dinner")
        self.assertEqual(payload["lanes"]["needs_review"]["total_items"], 1)
        self.assertEqual(
            payload["lanes"]["needs_review"]["items"][0]["action"],
            "protect",
        )
        self.assertEqual(payload["digest"]["total_items"], 3)
        self.assertEqual(payload["digest"]["showing_items"], 1)
        self.assertIn("#all/msg-", payload["digest"]["items"][0]["gmail_url"])
        self.assertEqual(payload["mailbox_actions"]["mailbox"], "inbox")
        self.assertEqual(len(payload["mailbox_actions"]["plans"]), 1)
        self.assertIn(
            "#inbox/msg-",
            payload["mailbox_actions"]["plans"][0]["gmail_url"],
        )
        self.assertEqual(payload["trash_gate"]["policy_enabled"], True)
        self.assertEqual(payload["audit"]["showing_events"], 1)
        self.assertIn("#all/msg-2", payload["audit"]["events"][0]["gmail_url"])
        self.assertEqual(
            [workflow["id"] for workflow in payload["workflows"]],
            [
                "sync",
                "classify",
                "daily-preview",
                "labels",
                "archive",
                "trash",
            ],
        )
        self.assertIn(
            "--mailbox inbox --limit 1",
            payload["workflows"][0]["primary_command"],
        )
        self.assertEqual(payload["workflows"][-1]["status"], "Policy enabled")
        self.assertEqual(payload["workflows"][-1]["count"], 1)
        self.assertTrue(payload["workflows"][-1]["mutates_gmail"])
        classify_workflow = payload["workflows"][1]
        self.assertEqual(classify_workflow["count"], 1)
        self.assertIn(
            "classify --mailbox inbox --limit 1",
            classify_workflow["primary_command"],
        )

    def test_build_daily_cockpit_payload_uses_trash_gmail_links_for_trash_scope(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-msg-1",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["TRASH"],
                    snippet="A useful local snippet.",
                    headers={
                        "From": "Sender <sender@example.com>",
                        "Subject": "Receipt",
                    },
                )
            },
            classifications={"msg-1": classification("msg-1")},
        )

        payload = build_daily_cockpit_payload(
            state,
            title_date="2026-05-26",
            mailbox="trash",
        )

        self.assertIn(
            "#trash/msg-1",
            payload["mailbox_actions"]["plans"][0]["gmail_url"],
        )

    def test_build_daily_cockpit_payload_rejects_negative_limits(self) -> None:
        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), limit=-1)

        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), audit_limit=-1)

        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), mailbox="spam")
