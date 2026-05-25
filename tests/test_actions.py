import unittest

from mailwyrm.actions import (
    ACTION_ARCHIVE_AFTER_DIGEST,
    ACTION_KEEP,
    ACTION_PROTECT,
    ACTION_REVIEW,
    ACTION_TRASH_AFTER_DIGEST,
    build_action_plans,
    plan_action,
    render_action_preview,
)
from mailwyrm.models import ClassificationCorrection, ClassificationRecord, MessageRecord
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

    def test_render_action_preview_normalizes_table_fields(self) -> None:
        plan = plan_action(
            message("msg-1", subject="Receipt\twith\nfolded whitespace"),
            classification("msg-1"),
        )

        preview = render_action_preview([plan])

        self.assertIn("Receipt with folded whitespace", preview)
        self.assertNotIn("Receipt\twith\nfolded whitespace", preview)


if __name__ == "__main__":
    unittest.main()
