import unittest

from mailwyrm.actions import (
    ACTION_ARCHIVE_AFTER_DIGEST,
    ACTION_KEEP,
    ACTION_PROTECT,
    ACTION_REVIEW,
    ACTION_RESTORE_ARCHIVE,
    ACTION_TRASH_AFTER_DIGEST,
    apply_archive_action_plans,
    build_action_plans,
    build_trash_preview,
    plan_action,
    render_action_preview,
    render_trash_preview,
    restore_archived_message,
)
from mailwyrm.models import (
    AutomationPolicy,
    ClassificationCorrection,
    ClassificationRecord,
    DigestAuditEvent,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState


def message(
    message_id: str = "msg-1",
    *,
    label_ids: list[str] | None = None,
    subject: str = "Hello",
    internal_date: str = "1710000000000",
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date=internal_date,
        label_ids=label_ids if label_ids is not None else ["INBOX"],
        snippet="Snippet",
        headers={"Subject": subject},
    )


def classification(
    message_id: str = "msg-1",
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


class ActionsTest(unittest.TestCase):
    def test_plan_action_keeps_human_mail(self) -> None:
        plan = plan_action(
            message(),
            classification(category="human", machine_type=None, suggested_actions=["review"]),
        )

        self.assertEqual(plan.action, ACTION_KEEP)

    def test_plan_action_protects_high_risk_mail(self) -> None:
        plan = plan_action(
            message(),
            classification(
                category="needs_review",
                machine_type="security",
                importance="high",
                automation_safety="low",
                confidence=0.74,
                suggested_actions=["review", "protect"],
            ),
        )

        self.assertEqual(plan.action, ACTION_PROTECT)

    def test_plan_action_reviews_low_confidence_machine_mail(self) -> None:
        plan = plan_action(message(), classification(confidence=0.7))

        self.assertEqual(plan.action, ACTION_REVIEW)

    def test_plan_action_archives_machine_mail_after_digest(self) -> None:
        plan = plan_action(message(), classification())

        self.assertEqual(plan.action, ACTION_ARCHIVE_AFTER_DIGEST)

    def test_plan_action_trashes_only_low_risk_machine_mail_after_digest(self) -> None:
        plan = plan_action(
            message(),
            classification(
                importance="low",
                automation_safety="high",
                confidence=0.94,
                suggested_actions=["digest", "trash"],
            ),
        )

        self.assertEqual(plan.action, ACTION_TRASH_AFTER_DIGEST)

    def test_build_action_plans_defaults_to_inbox(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", subject="Inbox"),
                "msg-2": message(
                    "msg-2",
                    label_ids=[],
                    subject="Archived",
                    internal_date="1710000000001",
                ),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
        )

        plans = build_action_plans(state)

        self.assertEqual([plan.message.id for plan in plans], ["msg-1"])

    def test_build_action_plans_can_include_all_mail(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", subject="Inbox"),
                "msg-2": message(
                    "msg-2",
                    label_ids=[],
                    subject="Archived",
                    internal_date="1710000000001",
                ),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
        )

        plans = build_action_plans(state, mailbox="all-mail")

        self.assertEqual([plan.message.id for plan in plans], ["msg-2", "msg-1"])

    def test_build_action_plans_respects_corrections(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1", category="human")},
            corrections={
                "msg-1": ClassificationCorrection(
                    message_id="msg-1",
                    category="machine",
                    machine_type="notification",
                    reason="Known notification.",
                )
            },
        )

        plans = build_action_plans(state)

        self.assertEqual(plans[0].action, ACTION_ARCHIVE_AFTER_DIGEST)

    def test_build_action_plans_respects_zero_limit(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )

        self.assertEqual(build_action_plans(state, limit=0), [])

    def test_render_action_preview_includes_counts_and_report(self) -> None:
        plans = [
            plan_action(message("msg-1", subject="Receipt"), classification("msg-1")),
            plan_action(
                message("msg-2", subject="Dinner"),
                classification("msg-2", category="human", machine_type=None),
            ),
        ]

        preview = render_action_preview(plans)

        self.assertIn("No Gmail actions will be performed.", preview)
        self.assertIn("- archive_after_digest: 1", preview)
        self.assertIn("- keep: 1", preview)
        self.assertIn("Message ID\tAction\tCategory\tConfidence\tSubject\tReason", preview)
        self.assertIn("msg-1\tarchive_after_digest\tmachine\t0.86\tReceipt", preview)

    def test_render_action_preview_can_show_mutation_notice(self) -> None:
        plans = [
            plan_action(message("msg-1", subject="Receipt"), classification("msg-1")),
        ]

        preview = render_action_preview(plans, mutates_gmail=True)

        self.assertIn("Gmail will be modified after this preview.", preview)
        self.assertNotIn("No Gmail actions will be performed.", preview)

    def test_render_action_preview_normalizes_table_fields(self) -> None:
        plan = plan_action(
            message("msg-1", subject="Receipt\twith\nfolded whitespace"),
            classification("msg-1"),
        )

        preview = render_action_preview([plan])

        self.assertIn("Receipt with folded whitespace", preview)
        self.assertNotIn("Receipt\twith\nfolded whitespace", preview)

    def test_build_trash_preview_requires_policy(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                )
            },
            digest_audit_events=[digest_event("msg-1")],
        )

        preview = build_trash_preview(state)

        self.assertFalse(preview.policy_enabled)
        self.assertEqual(preview.plans, [])
        self.assertEqual(preview.skipped_policy_disabled, 1)

    def test_build_trash_preview_requires_digest_event(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                )
            },
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        preview = build_trash_preview(state)

        self.assertTrue(preview.policy_enabled)
        self.assertEqual(preview.plans, [])
        self.assertEqual(preview.skipped_not_digested, 1)

    def test_build_trash_preview_returns_digested_trash_candidates(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                )
            },
            digest_audit_events=[digest_event("msg-1")],
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        preview = build_trash_preview(state)

        self.assertEqual([plan.message.id for plan in preview.plans], ["msg-1"])

    def test_render_trash_preview_reports_policy_and_candidates(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", subject="Promo")},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    importance="low",
                    automation_safety="high",
                    confidence=0.94,
                    suggested_actions=["digest", "trash"],
                )
            },
            digest_audit_events=[digest_event("msg-1")],
            automation_policy=AutomationPolicy(trash_after_digest_enabled=True),
        )

        report = render_trash_preview(build_trash_preview(state))

        self.assertIn("Mailbox Trash Preview", report)
        self.assertIn("No Gmail actions will be performed.", report)
        self.assertIn("Trash policy: enabled", report)
        self.assertIn("msg-1\ttrash_after_digest\tmachine\t0.94\tPromo", report)

    def test_apply_archive_action_plans_removes_inbox_and_audits(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", label_ids=["INBOX", "Label_1"])},
            classifications={"msg-1": classification("msg-1")},
        )
        state.digest_audit_events.append(
            digest_event("msg-1", classifier_version="rules-v0")
        )
        plans = build_action_plans(state)
        client = FakeGmailClient()

        result = apply_archive_action_plans(client, state, plans)

        self.assertEqual(result.applied, 1)
        self.assertEqual(result.skipped_not_digested, 0)
        self.assertEqual(client.removed, [("msg-1", ["INBOX"])])
        self.assertEqual(state.messages["msg-1"].label_ids, ["Label_1"])
        self.assertEqual(state.label_audit_events[0].action, ACTION_ARCHIVE_AFTER_DIGEST)
        self.assertEqual(state.label_audit_events[0].label_ids, ["INBOX"])
        self.assertEqual(
            state.label_audit_events[0].reason,
            "Automated sender or subject pattern.",
        )

    def test_apply_archive_action_plans_skips_undigested_messages(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )
        plans = build_action_plans(state)
        client = FakeGmailClient()

        result = apply_archive_action_plans(client, state, plans)

        self.assertEqual(result.applied, 0)
        self.assertEqual(result.skipped_not_digested, 1)
        self.assertEqual(client.removed, [])
        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX"])
        self.assertEqual(state.label_audit_events, [])

    def test_apply_archive_action_plans_skips_non_archive_actions(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1", category="human")},
        )
        state.digest_audit_events.append(digest_event("msg-1"))
        plans = build_action_plans(state)
        client = FakeGmailClient()

        result = apply_archive_action_plans(client, state, plans)

        self.assertEqual(result.applied, 0)
        self.assertEqual(result.skipped_not_digested, 0)
        self.assertEqual(client.removed, [])
        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX"])
        self.assertEqual(state.label_audit_events, [])

    def test_apply_archive_action_plans_skips_already_archived_messages(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", label_ids=[])},
            classifications={"msg-1": classification("msg-1")},
        )
        plans = build_action_plans(state, mailbox="all-mail")
        client = FakeGmailClient()

        result = apply_archive_action_plans(client, state, plans)

        self.assertEqual(result.applied, 0)
        self.assertEqual(result.skipped_not_digested, 0)
        self.assertEqual(client.removed, [])
        self.assertEqual(state.messages["msg-1"].label_ids, [])
        self.assertEqual(state.label_audit_events, [])

    def test_restore_archived_message_adds_inbox_and_audits(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1", label_ids=["Label_1"])},
            classifications={"msg-1": classification("msg-1")},
        )
        client = FakeGmailClient()

        restored = restore_archived_message(client, state, "msg-1")

        self.assertTrue(restored)
        self.assertEqual(client.added, [("msg-1", ["INBOX"])])
        self.assertEqual(state.messages["msg-1"].label_ids, ["Label_1", "INBOX"])
        self.assertEqual(state.label_audit_events[0].action, ACTION_RESTORE_ARCHIVE)
        self.assertEqual(
            state.label_audit_events[0].reason,
            "User restored archived message to inbox.",
        )
        self.assertEqual(state.label_audit_events[0].classifier_version, "rules-v0")

    def test_restore_archived_message_skips_already_inbox_messages(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})
        client = FakeGmailClient()

        restored = restore_archived_message(client, state, "msg-1")

        self.assertFalse(restored)
        self.assertEqual(client.added, [])
        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX"])
        self.assertEqual(state.label_audit_events, [])

    def test_restore_archived_message_rejects_unknown_message(self) -> None:
        state = MailwyrmState()
        client = FakeGmailClient()

        with self.assertRaisesRegex(ValueError, "not in the local index"):
            restore_archived_message(client, state, "msg-1")

        self.assertEqual(client.added, [])


class FakeGmailClient:
    def __init__(self) -> None:
        self.added: list[tuple[str, list[str]]] = []
        self.removed: list[tuple[str, list[str]]] = []

    def add_labels_to_message(self, message_id: str, label_ids: list[str]) -> None:
        self.added.append((message_id, label_ids))

    def remove_labels_from_message(self, message_id: str, label_ids: list[str]) -> None:
        self.removed.append((message_id, label_ids))


def digest_event(message_id: str, classifier_version: str = "rules-v0"):
    return DigestAuditEvent(
        message_id=message_id,
        digest_title_date="2026-05-25",
        reason="Automated sender or subject pattern.",
        classifier_version=classifier_version,
        created_at="2026-05-25T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
