import unittest

from mailwyrm.corrections import (
    CorrectionError,
    add_correction,
    correction_report,
    effective_classification,
)
from mailwyrm.models import ClassificationCorrection, ClassificationRecord, MessageRecord
from mailwyrm.store import MailwyrmState


def message(message_id: str = "msg-1") -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="A useful snippet.",
        headers={"Subject": "Weekly update"},
    )


def classification(message_id: str = "msg-1") -> ClassificationRecord:
    return ClassificationRecord(
        message_id=message_id,
        category="needs_review",
        machine_type=None,
        review_type="unknown",
        importance="medium",
        automation_safety="low",
        confidence=0.55,
        reason="No strong human or machine signal.",
        suggested_actions=["review"],
        classifier_version="rules-v0",
    )


def missing_correction() -> ClassificationCorrection:
    return ClassificationCorrection(
        message_id="missing",
        category="human",
        machine_type=None,
        reason="Legacy correction.",
    )


class CorrectionsTest(unittest.TestCase):
    def test_adds_valid_correction(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        correction = add_correction(
            state,
            message_id="msg-1",
            category="machine",
            machine_type="news",
            reason="Known news.",
        )

        self.assertEqual(correction.category, "machine")
        self.assertEqual(state.corrections["msg-1"].machine_type, "news")

    def test_rejects_unknown_message(self) -> None:
        state = MailwyrmState()

        with self.assertRaises(CorrectionError):
            add_correction(state, message_id="missing", category="human")

    def test_rejects_machine_type_for_non_machine_category(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        with self.assertRaises(CorrectionError):
            add_correction(
                state,
                message_id="msg-1",
                category="human",
                machine_type="news",
            )

    def test_rejects_unknown_machine_type(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        with self.assertRaises(CorrectionError):
            add_correction(
                state,
                message_id="msg-1",
                category="machine",
                machine_type="made_up",
            )

    def test_defaults_machine_type_for_machine_correction(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        correction = add_correction(state, message_id="msg-1", category="machine")

        self.assertEqual(correction.machine_type, "transactional")

    def test_effective_classification_preserves_original_with_user_overlay(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})
        correction = add_correction(
            state,
            message_id="msg-1",
            category="machine",
            machine_type="news",
            reason="Known news.",
        )

        effective = effective_classification(classification("msg-1"), correction)

        self.assertEqual(effective.category, "machine")
        self.assertEqual(effective.machine_type, "news")
        self.assertIsNone(effective.review_type)
        self.assertEqual(effective.confidence, 1.0)
        self.assertEqual(effective.reason, "Known news.")
        self.assertEqual(effective.classifier_version, "rules-v0+user-correction")

    def test_correction_report_counts_category_changes(self) -> None:
        state = MailwyrmState(
            messages={"msg-1": message("msg-1")},
            classifications={"msg-1": classification("msg-1")},
        )
        add_correction(state, message_id="msg-1", category="machine")

        report = correction_report(state)

        self.assertIn("Corrections: 1", report)
        self.assertIn("Category changes: 1", report)
        self.assertIn("Weekly update", report)

    def test_correction_report_handles_missing_messages(self) -> None:
        state = MailwyrmState()
        state.corrections["missing"] = missing_correction()

        report = correction_report(state)

        self.assertIn("Corrections: 1", report)
        self.assertIn("(missing message)", report)


if __name__ == "__main__":
    unittest.main()
