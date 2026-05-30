import unittest
from pathlib import Path

from mailwyrm.cockpit import build_daily_cockpit_payload, build_message_detail_payload
from mailwyrm.models import (
    AutomationPolicy,
    ClassificationCorrection,
    ClassificationRecord,
    DigestAuditEvent,
    FollowUpMarker,
    ReadLaterMarker,
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


def message_with_body(message_id: str, subject: str, body_text: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX", "Label_1"],
        snippet="A useful local snippet.",
        headers={
            "From": "Sender <sender@example.com>",
            "To": "User <user@example.com>",
            "Subject": subject,
            "Date": "Tue, 26 May 2026 10:00:00 -0600",
            "Message-ID": "<msg-1@example.com>",
        },
        body_text=body_text,
    )


def classification(
    message_id: str,
    *,
    category: str = "machine",
    machine_type: str | None = "notification",
    review_type: str | None = None,
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
        review_type=review_type,
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
                    machine_type=None,
                    review_type="security",
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
            client_secret=Path("/Users/dave/code/client_secret.json"),
        )

        self.assertEqual(payload["date"], "2026-05-26")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["account"]["email"], "user@example.com")
        self.assertIsNone(payload["account"]["avatar_url"])
        self.assertEqual(payload["attention"]["machine"], 2)
        self.assertEqual(payload["lanes"]["human"]["total_items"], 1)
        self.assertEqual(payload["lanes"]["human"]["items"][0]["subject"], "Dinner")
        self.assertEqual(payload["lanes"]["needs_review"]["total_items"], 1)
        self.assertEqual(
            payload["lanes"]["needs_review"]["items"][0]["action"],
            "protect",
        )
        self.assertEqual(
            payload["lanes"]["needs_review"]["items"][0]["review_type"],
            "security",
        )
        self.assertEqual(payload["lanes"]["needs_review"]["review_types"]["security"], 1)
        self.assertEqual(payload["digest"]["total_items"], 3)
        self.assertEqual(payload["digest"]["showing_items"], 1)
        self.assertIn("#all/msg-", payload["digest"]["items"][0]["gmail_url"])
        self.assertEqual(payload["digest"]["bundles"][0]["action"], "trash")
        self.assertTrue(
            payload["digest"]["bundles"][0]["action_label"].startswith("Got it: trash")
        )
        self.assertIn("sender_groups", payload["digest"]["bundles"][0])
        self.assertEqual(payload["mailbox_actions"]["mailbox"], "inbox")
        self.assertEqual(payload["mailbox_actions"]["showing_plans"], 1)
        self.assertEqual(payload["mailbox_actions"]["total_plans"], 4)
        self.assertEqual(len(payload["mailbox_actions"]["plans"]), 1)
        self.assertIn(
            "#inbox/msg-",
            payload["mailbox_actions"]["plans"][0]["gmail_url"],
        )
        self.assertEqual(payload["cleanup"]["mailbox"], "inbox")
        self.assertEqual(payload["cleanup"]["archive"]["candidates"], 1)
        self.assertEqual(payload["cleanup"]["archive"]["ready"], 0)
        self.assertEqual(payload["cleanup"]["archive"]["waiting_for_digest"], 1)
        self.assertEqual(payload["cleanup"]["trash"]["ready"], 0)
        self.assertEqual(payload["cleanup"]["clearable_now"], 0)
        self.assertEqual(payload["cleanup"]["kept_human"], 0)
        self.assertEqual(payload["cleanup"]["protected_or_review"], 0)
        self.assertTrue(payload["configuration"]["client_secret_configured"])
        self.assertNotIn("features", payload)
        self.assertIn(
            "--client-secret /Users/dave/code/client_secret.json",
            payload["cleanup"]["archive"]["apply_command"],
        )
        self.assertIn(
            "--client-secret /Users/dave/code/client_secret.json",
            payload["workflows"][0]["primary_command"],
        )
        self.assertIn(
            "--client-secret /Users/dave/code/client_secret.json",
            payload["commands"][0],
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
        self.assertEqual(payload["workflows"][0]["app_action"], "sync")
        self.assertEqual(payload["workflows"][0]["title"], "Full sync from Gmail")
        self.assertEqual(payload["workflows"][0]["action_label"], "Run full sync")
        self.assertTrue(payload["workflows"][0]["sync_all"])
        self.assertEqual(payload["workflows"][-1]["status"], "Policy enabled")
        self.assertEqual(payload["workflows"][-1]["count"], 1)
        self.assertTrue(payload["workflows"][-1]["mutates_gmail"])
        classify_workflow = payload["workflows"][1]
        self.assertEqual(classify_workflow["count"], 1)
        self.assertEqual(classify_workflow["app_action"], "classify")
        self.assertEqual(classify_workflow["action_label"], "Classify")
        self.assertTrue(classify_workflow["process_all"])
        self.assertIn(
            "classify --mailbox inbox --limit 1",
            classify_workflow["primary_command"],
        )
        labels_workflow = payload["workflows"][3]
        self.assertEqual(labels_workflow["app_action"], "labels")
        self.assertEqual(labels_workflow["action_label"], "Apply labels")
        archive_workflow = payload["workflows"][4]
        self.assertEqual(archive_workflow["app_action"], "archive")
        self.assertEqual(archive_workflow["action_label"], "Archive")
        trash_workflow = payload["workflows"][5]
        self.assertEqual(trash_workflow["app_action"], "trash")
        self.assertEqual(trash_workflow["action_label"], "Move to Trash")

    def test_review_resolution_moves_message_from_review_to_digest_bundle(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Morning headlines")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="needs_review",
                    machine_type=None,
                    review_type="uncertain_machine",
                    importance="medium",
                    automation_safety="low",
                    suggested_actions=["review", "protect"],
                )
            },
            corrections={
                "msg-1": ClassificationCorrection(
                    message_id="msg-1",
                    category="machine",
                    machine_type="news",
                    reason="User resolved this from the Review card.",
                    suggested_actions=["digest"],
                    importance="medium",
                    automation_safety="medium",
                )
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        self.assertEqual(payload["lanes"]["needs_review"]["total_items"], 0)
        self.assertEqual(payload["attention"]["machine"], 1)
        self.assertEqual(payload["digest"]["bundles"][0]["title"], "News")
        self.assertEqual(
            payload["digest"]["bundles"][0]["sender_groups"][0]["subject"],
            "Morning headlines",
        )
        self.assertEqual(
            payload["digest"]["bundles"][0]["sender_groups"][0]["summary"],
            "A useful local snippet.",
        )

    def test_digest_bundle_payload_groups_same_sender_rows(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message_with_body(
                    "msg-1",
                    "Copilot finished one",
                    "Build completed with failing lint checks.",
                ),
                "msg-2": message_with_body(
                    "msg-2",
                    "Copilot finished two",
                    "Pull request review is ready.",
                ),
                "msg-3": MessageRecord(
                    id="msg-3",
                    thread_id="thread-msg-3",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["INBOX"],
                    snippet="Another sender.",
                    headers={
                        "From": "GitHub <notifications@github.com>",
                        "Subject": "Issue update",
                    },
                ),
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="product_community",
                ),
                "msg-2": classification(
                    "msg-2",
                    category="machine",
                    machine_type="product_community",
                ),
                "msg-3": classification(
                    "msg-3",
                    category="machine",
                    machine_type="product_community",
                ),
            },
            followups={
                "msg-2": FollowUpMarker(
                    message_id="msg-2",
                    reason="Needs a reply.",
                    created_at="2026-05-25T00:00:00+00:00",
                )
            },
            read_later={
                "msg-1": ReadLaterMarker(
                    message_id="msg-1",
                    reason="Worth reading.",
                    created_at="2026-05-25T00:00:00+00:00",
                )
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        groups = payload["digest"]["bundles"][0]["sender_groups"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["sender_email"], "sender@example.com")
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(groups[0]["message_ids"], ["msg-1", "msg-2"])
        self.assertEqual(
            groups[0]["messages"],
            [
                {
                    "message_id": "msg-1",
                    "subject": "Copilot finished one",
                    "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg-1",
                },
                {
                    "message_id": "msg-2",
                    "subject": "Copilot finished two",
                    "gmail_url": "https://mail.google.com/mail/u/0/#inbox/msg-2",
                },
            ],
        )
        self.assertEqual(groups[0]["followup_count"], 1)
        self.assertEqual(groups[0]["read_later_count"], 1)
        self.assertEqual(groups[0]["subject"], "")
        self.assertEqual(
            groups[0]["summary"],
            "2 messages: Copilot finished one - Build completed with failing lint checks.; "
            "Copilot finished two - Pull request review is ready.",
        )
        self.assertEqual(groups[1]["sender_email"], "notifications@github.com")
        self.assertEqual(groups[1]["subject"], "Issue update")

    def test_digest_bundle_payload_keeps_news_as_headline_rows(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "First headline"),
                "msg-2": message("msg-2", "Second headline"),
            },
            classifications={
                "msg-1": classification("msg-1", category="machine", machine_type="news"),
                "msg-2": classification("msg-2", category="machine", machine_type="news"),
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        groups = payload["digest"]["bundles"][0]["sender_groups"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["sender_email"], "sender@example.com")
        self.assertEqual(groups[0]["count"], 1)
        self.assertEqual(groups[0]["subject"], "First headline")
        self.assertEqual(groups[1]["sender_email"], "sender@example.com")
        self.assertEqual(groups[1]["count"], 1)
        self.assertEqual(groups[1]["subject"], "Second headline")

    def test_digest_summary_omits_tracking_url_noise(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message_with_body(
                    "msg-1",
                    "Inside Lucy",
                    (
                        "<https://s22aeml01blkbs02.blob.core.windows.net/emailimages/"
                        "2026/5/tracking-image-reference.png>\n"
                        "News <https://eml-peur01.app.blackbaud.net/intv2/j/"
                        "D9D3D6FF-EC69-451F-9461-1C10D25FB1FA/r/link>\n"
                        "The President's Monthly Message"
                    ),
                )
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="product_community",
                )
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")
        summary = payload["digest"]["bundles"][0]["sender_groups"][0]["summary"]

        self.assertEqual(summary, "News The President's Monthly Message")
        self.assertNotIn("https://", summary)

    def test_digest_summary_suppresses_markdown_heading_marker(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message_with_body(
                    "msg-1",
                    "Shipment update",
                    (
                        "AliceIOT: https://production.alice-iot.app\n"
                        "# Hi DAVID CHRISTIANSEN\n"
                        "Your shipment is awaiting customs release."
                    ),
                )
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="transactional",
                )
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")
        summary = payload["digest"]["bundles"][0]["sender_groups"][0]["summary"]

        self.assertIn("Hi DAVID CHRISTIANSEN", summary)
        self.assertNotIn("# Hi", summary)

    def test_build_daily_cockpit_payload_uses_placeholder_without_client_secret(self) -> None:
        payload = build_daily_cockpit_payload(
            MailwyrmState(messages={"msg-1": message("msg-1", "Receipt")}),
            title_date="2026-05-26",
        )

        self.assertFalse(payload["configuration"]["client_secret_configured"])
        self.assertIn(
            "--client-secret /path/to/client_secret.json",
            payload["commands"][0],
        )

    def test_real_people_lane_groups_messages_by_sender(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-msg-1",
                    history_id="10",
                    internal_date="1710000000002",
                    label_ids=["INBOX"],
                    snippet="First note.",
                    headers={
                        "From": "Ada Lovelace <ada@example.com>",
                        "Subject": "First",
                    },
                ),
                "msg-2": MessageRecord(
                    id="msg-2",
                    thread_id="thread-msg-2",
                    history_id="10",
                    internal_date="1710000000001",
                    label_ids=["INBOX"],
                    snippet="Second note.",
                    headers={
                        "From": "Ada Lovelace <ada@example.com>",
                        "Subject": "Second",
                    },
                ),
                "msg-3": MessageRecord(
                    id="msg-3",
                    thread_id="thread-msg-3",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["INBOX"],
                    snippet="Other note.",
                    headers={
                        "From": "Grace Hopper <grace@example.com>",
                        "Subject": "Other",
                    },
                ),
            },
            classifications={
                "msg-1": classification("msg-1", category="human", machine_type=None),
                "msg-2": classification("msg-2", category="human", machine_type=None),
                "msg-3": classification("msg-3", category="human", machine_type=None),
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        people = payload["lanes"]["human"]["people"]
        self.assertEqual(len(people), 2)
        self.assertEqual(people[0]["name"], "Ada Lovelace")
        self.assertEqual(people[0]["email"], "ada@example.com")
        self.assertEqual(people[0]["count"], 2)
        self.assertEqual(people[0]["conversation_count"], 2)
        self.assertEqual(
            [item["subject"] for item in people[0]["items"]],
            ["First", "Second"],
        )
        self.assertEqual(
            [item["message_count"] for item in people[0]["items"]],
            [1, 1],
        )
        self.assertEqual(people[1]["name"], "Grace Hopper")

    def test_real_people_lane_collapses_messages_by_thread_within_person(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-shared",
                    history_id="10",
                    internal_date="1710000000003",
                    label_ids=["INBOX"],
                    snippet="Latest reply.",
                    headers={
                        "From": "Ada Lovelace <ada@example.com>",
                        "Subject": "Re: Introductions",
                    },
                ),
                "msg-2": MessageRecord(
                    id="msg-2",
                    thread_id="thread-shared",
                    history_id="10",
                    internal_date="1710000000002",
                    label_ids=["INBOX"],
                    snippet="Earlier reply.",
                    headers={
                        "From": "Ada Lovelace <ada@example.com>",
                        "Subject": "Re: Introductions",
                    },
                ),
                "msg-3": MessageRecord(
                    id="msg-3",
                    thread_id="thread-other",
                    history_id="10",
                    internal_date="1710000000001",
                    label_ids=["INBOX"],
                    snippet="Separate conversation.",
                    headers={
                        "From": "Ada Lovelace <ada@example.com>",
                        "Subject": "Lunch",
                    },
                ),
            },
            classifications={
                "msg-1": classification("msg-1", category="human", machine_type=None),
                "msg-2": classification("msg-2", category="human", machine_type=None),
                "msg-3": classification("msg-3", category="human", machine_type=None),
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        person = payload["lanes"]["human"]["people"][0]
        self.assertEqual(person["count"], 3)
        self.assertEqual(person["conversation_count"], 2)
        self.assertEqual(len(person["items"]), 2)
        self.assertEqual(person["items"][0]["thread_id"], "thread-shared")
        self.assertEqual(person["items"][0]["message_id"], "msg-1")
        self.assertEqual(person["items"][0]["message_count"], 2)
        self.assertEqual(person["items"][0]["message_ids"], ["msg-1", "msg-2"])
        self.assertEqual(person["items"][0]["snippet"], "Latest reply.")
        self.assertEqual(person["items"][1]["thread_id"], "thread-other")
        self.assertEqual(person["items"][1]["message_count"], 1)

    def test_review_type_counts_skip_non_needs_review_items(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Low confidence machine")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="machine",
                    machine_type="marketing",
                    confidence=0.7,
                    suggested_actions=["digest"],
                )
            },
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox")

        self.assertEqual(payload["lanes"]["needs_review"]["total_items"], 1)
        self.assertEqual(payload["lanes"]["needs_review"]["review_types"], {})
        self.assertIsNone(payload["lanes"]["needs_review"]["items"][0]["review_type"])

    def test_cleanup_archive_candidates_ignore_already_archived_mail(self) -> None:
        archived = MessageRecord(
            id="msg-1",
            thread_id="thread-msg-1",
            history_id="10",
            internal_date="1710000000000",
            label_ids=[],
            snippet="A useful local snippet.",
            headers={"From": "Sender <sender@example.com>", "Subject": "Receipt"},
        )
        state = MailwyrmState(
            messages={"msg-1": archived},
            classifications={"msg-1": classification("msg-1")},
        )

        payload = build_daily_cockpit_payload(state, mailbox="all-mail")

        self.assertEqual(payload["cleanup"]["archive"]["candidates"], 0)
        self.assertEqual(payload["cleanup"]["archive"]["waiting_for_digest"], 0)

    def test_cleanup_trash_counts_use_limited_action_plans(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", "First promo"),
                "msg-2": message("msg-2", "Second promo"),
            },
            classifications={
                "msg-1": classification(
                    "msg-1",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                ),
                "msg-2": classification(
                    "msg-2",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                ),
            },
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        payload = build_daily_cockpit_payload(state, mailbox="inbox", limit=1)

        self.assertEqual(payload["cleanup"]["trash"]["candidates"], 1)
        self.assertEqual(payload["cleanup"]["trash"]["waiting_for_digest"], 1)
        self.assertEqual(payload["cleanup"]["trash"]["ready"], 0)

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

    def test_build_message_detail_payload_combines_local_message_context(self) -> None:
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
                    machine_type="delivery",
                    review_type=None,
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                )
            },
            label_audit_events=[
                LabelAuditEvent(
                    message_id="msg-1",
                    action="archive_after_digest",
                    label_names=["INBOX"],
                    label_ids=["INBOX"],
                    reason="Archived after digest.",
                    classifier_version="rules-v0",
                    created_at="2026-05-26T00:00:00+00:00",
                )
            ],
        )

        payload = build_message_detail_payload(
            state,
            message_id="msg-1",
            mailbox="inbox",
        )

        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["message"]["subject"], "Delivery update")
        self.assertEqual(payload["message"]["body_text"], "Package arrives Friday by 8 PM.")
        self.assertTrue(payload["message"]["has_body_text"])
        self.assertFalse(payload["reply_available"])
        self.assertEqual(payload["reply_status"], "Draft replies are not enabled yet.")
        self.assertEqual(payload["classification"]["machine_type"], "delivery")
        self.assertIsNone(payload["classification"]["review_type"])
        self.assertFalse(payload["review_resolution"]["available"])
        self.assertEqual(payload["suggested_action"]["action"], "trash_after_digest")
        self.assertTrue(payload["suggested_action"]["mutates_gmail"])
        self.assertEqual(payload["audit"][0]["action"], "archive_after_digest")
        self.assertIn("#inbox/msg-1", payload["message"]["gmail_url"])

    def test_build_message_detail_payload_includes_thread_conversation(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": MessageRecord(
                    id="msg-1",
                    thread_id="thread-1",
                    history_id="10",
                    internal_date="1710000000000",
                    label_ids=["INBOX"],
                    snippet="First note.",
                    headers={
                        "From": "Ada <ada@example.com>",
                        "Subject": "Re: Reading",
                        "Date": "Tue, 26 May 2026 09:00:00 -0600",
                    },
                    body_text="First note body.",
                ),
                "msg-2": MessageRecord(
                    id="msg-2",
                    thread_id="thread-1",
                    history_id="11",
                    internal_date="1710000001000",
                    label_ids=["INBOX"],
                    snippet="Second note.",
                    headers={
                        "From": "Dave <dave@example.com>",
                        "Subject": "Re: Reading",
                        "Date": "Tue, 26 May 2026 09:05:00 -0600",
                    },
                    body_text="Second note body.",
                ),
                "msg-3": message("msg-3", "Other thread"),
            },
        )

        payload = build_message_detail_payload(state, message_id="msg-2")

        self.assertEqual(
            [message["message_id"] for message in payload["conversation"]],
            ["msg-1", "msg-2"],
        )
        self.assertFalse(payload["conversation"][0]["selected"])
        self.assertTrue(payload["conversation"][1]["selected"])
        self.assertEqual(payload["conversation"][0]["body_text"], "First note body.")

    def test_build_message_detail_payload_handles_unclassified_messages(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1", "Unclassified")})

        payload = build_message_detail_payload(state, message_id="msg-1")

        self.assertIsNone(payload["classification"])
        self.assertIsNone(payload["suggested_action"])

    def test_build_message_detail_payload_includes_review_type(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Security alert")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="needs_review",
                    machine_type=None,
                    review_type="security",
                    importance="high",
                    automation_safety="low",
                    suggested_actions=["review", "protect"],
                )
            },
        )

        payload = build_message_detail_payload(state, message_id="msg-1")

        self.assertEqual(payload["classification"]["review_type"], "security")
        self.assertTrue(payload["review_resolution"]["available"])
        self.assertEqual(
            [resolution["id"] for resolution in payload["review_resolution"]["resolutions"]],
            ["human"],
        )
        self.assertIn("marketing", payload["review_resolution"]["machine_types"])
        self.assertIn("spam", payload["review_resolution"]["machine_types"])

    def test_build_message_detail_payload_defaults_missing_review_type(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Legacy review")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="needs_review",
                    machine_type=None,
                    review_type=None,
                    importance="medium",
                    automation_safety="low",
                    suggested_actions=["review"],
                )
            },
        )

        payload = build_message_detail_payload(state, message_id="msg-1")

        self.assertEqual(payload["classification"]["review_type"], "unknown")

    def test_build_message_detail_payload_includes_correction_without_classification(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", "Corrected")},
            corrections={
                "msg-1": ClassificationCorrection(
                    message_id="msg-1",
                    category="machine",
                    machine_type="newsletter",
                    reason="User correction.",
                )
            },
        )

        payload = build_message_detail_payload(state, message_id="msg-1")

        self.assertIsNone(payload["classification"])
        self.assertEqual(payload["correction"]["category"], "machine")
        self.assertEqual(payload["correction"]["machine_type"], "newsletter")

    def test_build_message_detail_payload_rejects_missing_messages(self) -> None:
        with self.assertRaises(KeyError):
            build_message_detail_payload(MailwyrmState(), message_id="missing")

    def test_build_daily_cockpit_payload_rejects_negative_limits(self) -> None:
        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), limit=-1)

        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), audit_limit=-1)

        with self.assertRaises(ValueError):
            build_daily_cockpit_payload(MailwyrmState(), mailbox="spam")
