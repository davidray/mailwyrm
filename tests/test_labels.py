import unittest

from mailwyrm.gmail import GmailLabel
from mailwyrm.labels import (
    apply_digested_label_plans,
    apply_label_plans,
    build_digested_label_plans,
    build_label_plans,
    labels_for_classification,
    render_digested_label_preview,
    render_label_preview,
)
from mailwyrm.models import ClassificationRecord, DigestAuditEvent, MessageRecord
from mailwyrm.store import MailwyrmState


def message(message_id: str = "msg-1") -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="Snippet",
        headers={"Subject": "Hello"},
    )


def archived_message(message_id: str = "msg-2") -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-2",
        history_id="11",
        internal_date="1710000000001",
        label_ids=[],
        snippet="Snippet",
        headers={"Subject": "Archived"},
    )


def trashed_message(message_id: str = "msg-3") -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-3",
        history_id="12",
        internal_date="1710000000002",
        label_ids=["TRASH"],
        snippet="Snippet",
        headers={"Subject": "Trashed"},
    )


def classification(
    message_id: str = "msg-1",
    *,
    category: str = "machine",
    importance: str = "medium",
    automation_safety: str = "medium",
) -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category=category,
        machine_type="notification" if category == "machine" else None,
        importance=importance,
        automation_safety=automation_safety,
        confidence=0.82,
        reason="Automated sender or subject pattern.",
        suggested_actions=["digest"] if category == "machine" else ["review"],
        classifier_version="rules-v0",
    )


class FakeGmailClient:
    def __init__(self) -> None:
        self.applied: list[tuple[str, list[str]]] = []
        self.ensured = 0
        self.ensured_names: list[tuple[str, ...]] = []

    def ensure_mailwyrm_labels(self, label_names=None):
        self.ensured += 1
        labels = {
            "Mailwyrm/Human": GmailLabel(id="label-human", name="Mailwyrm/Human"),
            "Mailwyrm/Machine": GmailLabel(id="label-machine", name="Mailwyrm/Machine"),
            "Mailwyrm/Needs Review": GmailLabel(
                id="label-review",
                name="Mailwyrm/Needs Review",
            ),
            "Mailwyrm/Digested": GmailLabel(
                id="label-digested",
                name="Mailwyrm/Digested",
            ),
            "Mailwyrm/Protected": GmailLabel(
                id="label-protected",
                name="Mailwyrm/Protected",
            ),
        }
        if label_names is None:
            return labels
        self.ensured_names.append(tuple(label_names))
        return {label_name: labels[label_name] for label_name in label_names}

    def add_labels_to_message(self, message_id: str, label_ids: list[str]) -> None:
        self.applied.append((message_id, label_ids))


class LabelsTest(unittest.TestCase):
    def test_labels_for_classification_maps_categories(self) -> None:
        self.assertEqual(
            labels_for_classification(classification(category="human")),
            ["Mailwyrm/Human"],
        )
        self.assertEqual(
            labels_for_classification(classification(category="machine")),
            ["Mailwyrm/Machine"],
        )

    def test_protected_review_gets_review_and_protected_labels(self) -> None:
        labels = labels_for_classification(
            classification(
                category="needs_review",
                importance="high",
                automation_safety="low",
            )
        )

        self.assertEqual(labels, ["Mailwyrm/Needs Review", "Mailwyrm/Protected"])

    def test_build_label_plans_respects_corrections(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={
                "msg-1": classification("msg-1", category="human"),
            },
        )
        from mailwyrm.models import ClassificationCorrection

        state.corrections["msg-1"] = ClassificationCorrection(
            message_id="msg-1",
            category="machine",
            machine_type="notification",
            reason="Known notification.",
        )

        plans = build_label_plans(state)

        self.assertEqual(plans[0].label_names, ["Mailwyrm/Machine"])

    def test_render_label_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )

        preview = render_label_preview(build_label_plans(state))

        self.assertIn("Message ID\tLabels\tSubject", preview)
        self.assertIn("msg-1\tMailwyrm/Machine\tHello", preview)

    def test_build_label_plans_defaults_to_inbox_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1"),
                "msg-2": archived_message("msg-2"),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
        )

        plans = build_label_plans(state)

        self.assertEqual([plan.message.id for plan in plans], ["msg-1"])

    def test_build_label_plans_all_mail_includes_archived_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1"),
                "msg-2": archived_message("msg-2"),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
            },
        )

        plans = build_label_plans(state, mailbox="all-mail")

        self.assertEqual([plan.message.id for plan in plans], ["msg-2", "msg-1"])

    def test_build_label_plans_trash_scope_includes_only_trashed_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1"),
                "msg-2": archived_message("msg-2"),
                "msg-3": trashed_message("msg-3"),
            },
            classifications={
                "msg-1": classification("msg-1"),
                "msg-2": classification("msg-2"),
                "msg-3": classification("msg-3"),
            },
        )

        plans = build_label_plans(state, mailbox="trash")

        self.assertEqual([plan.message.id for plan in plans], ["msg-3"])

    def test_build_label_plans_respects_zero_limit(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )

        self.assertEqual(build_label_plans(state, limit=0), [])

    def test_apply_label_plans_adds_missing_labels_and_audit_event(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )
        original_message = state.messages["msg-1"]
        client = FakeGmailClient()

        applied = apply_label_plans(client, state, build_label_plans(state))

        self.assertEqual(applied, 1)
        self.assertEqual(client.applied, [("msg-1", ["label-machine"])])
        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX", "label-machine"])
        self.assertIsNot(state.messages["msg-1"], original_message)
        self.assertEqual(state.label_audit_events[0].label_names, ["Mailwyrm/Machine"])

    def test_apply_label_plans_skips_already_labeled_messages(self) -> None:
        msg = message("msg-1")
        msg.label_ids.append("label-machine")
        state = MailwyrmState(
            messages={"msg-1": msg},
            classifications={"msg-1": classification("msg-1")},
        )
        client = FakeGmailClient()

        applied = apply_label_plans(client, state, build_label_plans(state))

        self.assertEqual(applied, 0)
        self.assertEqual(client.applied, [])
        self.assertEqual(state.label_audit_events, [])

    def test_apply_label_plans_returns_early_when_empty(self) -> None:
        state = MailwyrmState()
        client = FakeGmailClient()

        applied = apply_label_plans(client, state, [])

        self.assertEqual(applied, 0)
        self.assertEqual(client.ensured, 0)

    def test_apply_label_plans_audits_only_missing_labels(self) -> None:
        msg = message("msg-1")
        msg.label_ids.append("label-review")
        state = MailwyrmState(
            messages={"msg-1": msg},
            classifications={
                "msg-1": classification(
                    "msg-1",
                    category="needs_review",
                    importance="high",
                    automation_safety="low",
                )
            },
        )
        client = FakeGmailClient()

        applied = apply_label_plans(client, state, build_label_plans(state))

        self.assertEqual(applied, 1)
        self.assertEqual(client.applied, [("msg-1", ["label-protected"])])
        self.assertEqual(
            state.label_audit_events[0].label_names,
            ["Mailwyrm/Protected"],
        )
        self.assertEqual(state.label_audit_events[0].label_ids, ["label-protected"])

    def test_build_digested_label_plans_uses_digest_audit_events(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
        )

        plans = build_digested_label_plans(state)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].message.id, "msg-1")
        self.assertEqual(plans[0].label_name, "Mailwyrm/Digested")

    def test_build_digested_label_plans_skips_missing_messages_and_duplicates(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            digest_audit_events=[
                digest_event("missing"),
                digest_event("msg-1", title_date="2026-05-24"),
                digest_event("msg-1", title_date="2026-05-25"),
            ],
        )

        plans = build_digested_label_plans(state)

        self.assertEqual([plan.message.id for plan in plans], ["msg-1"])

    def test_render_digested_label_preview(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
        )

        preview = render_digested_label_preview(build_digested_label_plans(state))

        self.assertIn("Message ID\tLabels\tSubject", preview)
        self.assertIn("msg-1\tMailwyrm/Digested\tHello", preview)

    def test_apply_digested_label_plans_adds_missing_label_and_audit_event(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            digest_audit_events=[digest_event("msg-1")],
        )
        client = FakeGmailClient()

        applied = apply_digested_label_plans(
            client,
            state,
            build_digested_label_plans(state),
        )

        self.assertEqual(applied, 1)
        self.assertEqual(client.ensured_names, [("Mailwyrm/Digested",)])
        self.assertEqual(client.applied, [("msg-1", ["label-digested"])])
        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX", "label-digested"])
        self.assertEqual(state.label_audit_events[0].action, "add_digested_label")
        self.assertEqual(state.label_audit_events[0].label_names, ["Mailwyrm/Digested"])

    def test_apply_digested_label_plans_skips_already_labeled_messages(self) -> None:
        msg = message("msg-1")
        msg.label_ids.append("label-digested")
        state = MailwyrmState(
            messages={"msg-1": msg},
            digest_audit_events=[digest_event("msg-1")],
        )
        client = FakeGmailClient()

        applied = apply_digested_label_plans(
            client,
            state,
            build_digested_label_plans(state),
        )

        self.assertEqual(applied, 0)
        self.assertEqual(client.applied, [])
        self.assertEqual(state.label_audit_events, [])


def digest_event(message_id: str, title_date: str = "2026-05-25") -> DigestAuditEvent:
    return DigestAuditEvent(
        message_id=message_id,
        digest_title_date=title_date,
        reason="Automated sender or subject pattern.",
        classifier_version="rules-v0",
        created_at=f"{title_date}T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
