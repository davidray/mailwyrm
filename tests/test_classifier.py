import unittest

from mailwyrm.classifier import classify_message
from mailwyrm.models import MessageRecord


def message(
    *,
    sender: str,
    subject: str,
    snippet: str = "",
    body_text: str = "",
    message_id: str = "msg-1",
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet=snippet,
        headers={"From": sender, "Subject": subject},
        body_text=body_text,
    )


class ClassifierTest(unittest.TestCase):
    def test_classifies_machine_news(self) -> None:
        classification = classify_message(
            message(sender="Newsletter <newsletter@example.com>", subject="Weekly newsletter")
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "news")
        self.assertIn("digest", classification.suggested_actions)

    def test_classifies_machine_marketing(self) -> None:
        classification = classify_message(
            message(
                sender="Marketing <marketing@example.com>",
                subject="Limited time product discount",
                snippet="Unsubscribe from promotional offers any time.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "marketing")
        self.assertIn("digest", classification.suggested_actions)

    def test_classifies_machine_transactional(self) -> None:
        classification = classify_message(
            message(
                sender="Store <receipt@example.com>",
                subject="Your order receipt",
                snippet="Your order shipped and tracking is available.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "transactional")

    def test_classifies_machine_spam(self) -> None:
        classification = classify_message(
            message(
                sender="Winner <marketing@example.com>",
                subject="Limited time prize",
                snippet="Act now to claim your free money.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "spam")
        self.assertEqual(classification.automation_safety, "high")
        self.assertIn("trash", classification.suggested_actions)

    def test_classifies_machine_product_community(self) -> None:
        classification = classify_message(
            message(
                sender="Forum <community@example.com>",
                subject="New discussion in the product community",
                snippet="A member commented on your issue.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "product_community")

    def test_protects_high_risk_machine_mail(self) -> None:
        classification = classify_message(
            message(
                sender="Security <no-reply@example.com>",
                subject="Security alert for your account",
            )
        )

        self.assertEqual(classification.category, "needs_review")
        self.assertEqual(classification.importance, "high")
        self.assertEqual(classification.automation_safety, "low")
        self.assertIn("protect", classification.suggested_actions)

    def test_plain_word_risk_terms_do_not_match_inside_other_words(self) -> None:
        classification = classify_message(
            message(
                sender="Updates <no-reply@example.com>",
                subject="Contact preferences changed",
                snippet="Your contact preferences were updated.",
            )
        )

        self.assertNotEqual(classification.importance, "high")
        self.assertNotIn("protect", classification.suggested_actions)

    def test_classifies_reply_as_human(self) -> None:
        classification = classify_message(
            message(sender="Ada <ada@example.com>", subject="Re: dinner tomorrow")
        )

        self.assertEqual(classification.category, "human")
        self.assertIsNone(classification.machine_type)

    def test_classifies_github_copilot_notifications_as_trash_candidates(self) -> None:
        classification = classify_message(
            message(
                sender="GitHub <notifications@github.com>",
                subject="Re: [davidray/mailwyrm] Add policy-gated trash apply",
                snippet="copilot-pull-request-reviewer commented on this pull request.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "product_community")
        self.assertEqual(classification.importance, "low")
        self.assertEqual(classification.automation_safety, "high")
        self.assertGreaterEqual(classification.confidence, 0.9)
        self.assertIn("digest", classification.suggested_actions)
        self.assertIn("trash", classification.suggested_actions)

    def test_high_risk_github_copilot_notifications_still_protected(self) -> None:
        classification = classify_message(
            message(
                sender="GitHub <notifications@github.com>",
                subject="Security alert from Copilot",
                snippet="copilot-pull-request-reviewer mentioned account security.",
            )
        )

        self.assertEqual(classification.category, "needs_review")
        self.assertEqual(classification.importance, "high")
        self.assertEqual(classification.automation_safety, "low")
        self.assertIn("protect", classification.suggested_actions)

    def test_uses_body_text_for_classification_signals(self) -> None:
        classification = classify_message(
            message(
                sender="Updates <no-reply@example.com>",
                subject="Your weekly note",
                body_text="This newsletter includes product tips and an unsubscribe link.",
            )
        )

        self.assertEqual(classification.category, "machine")
        self.assertEqual(classification.machine_type, "news")
        self.assertIn("digest", classification.suggested_actions)


if __name__ == "__main__":
    unittest.main()
