from __future__ import annotations

import re
from email.utils import parseaddr

from mailwyrm.models import ClassificationRecord, MessageRecord


CLASSIFIER_VERSION = "rules-v0"

HIGH_RISK_TERMS = (
    "account recovery",
    "bank",
    "card",
    "fraud",
    "insurance",
    "invoice",
    "legal",
    "medical",
    "password",
    "payment",
    "security",
    "tax",
    "verification code",
)

MACHINE_SENDER_TERMS = (
    "alert",
    "billing",
    "bounce",
    "delivery",
    "do-not-reply",
    "donotreply",
    "hello@",
    "mailer",
    "marketing",
    "newsletter",
    "no-reply",
    "noreply",
    "notification",
    "notifications",
    "receipt",
    "reply@",
    "support@",
)

MACHINE_SUBJECT_TERMS = (
    "account update",
    "alert",
    "confirmation",
    "delivered",
    "delivery",
    "invoice",
    "newsletter",
    "order",
    "receipt",
    "renewal",
    "reset your password",
    "shipped",
    "statement",
    "subscription",
    "verification code",
    "welcome to",
)

HUMAN_REPLY_PREFIXES = ("re:", "fwd:", "fw:")


def classify_message(message: MessageRecord) -> ClassificationRecord:
    sender = message.headers.get("From", "")
    subject = message.headers.get("Subject", "")
    text = " ".join([sender, subject, message.snippet]).lower()
    sender_address = parseaddr(sender)[1].lower()

    high_risk = _contains_any(text, HIGH_RISK_TERMS)
    machine_score = _machine_score(sender_address, subject, text)
    human_reply_signal = subject.strip().lower().startswith(HUMAN_REPLY_PREFIXES)

    if high_risk:
        category = "needs_review"
        machine_type = _machine_type(text)
        importance = "high"
        automation_safety = "low"
        confidence = 0.74
        reason = "High-risk account, payment, security, legal, medical, or similar topic."
        suggested_actions = ["review", "protect"]
    elif _is_github_copilot_notification(sender_address, text):
        category = "machine"
        machine_type = "notification"
        importance = "low"
        automation_safety = "high"
        confidence = 0.94
        reason = "Low-risk Copilot notification from GitHub."
        suggested_actions = ["digest", "trash"]
    elif machine_score >= 2 and not human_reply_signal:
        category = "machine"
        machine_type = _machine_type(text)
        importance = "low" if machine_type in {"newsletter", "delivery"} else "medium"
        automation_safety = "medium"
        confidence = min(0.95, 0.62 + (machine_score * 0.1))
        reason = "Automated sender or subject pattern."
        suggested_actions = ["digest"]
    elif human_reply_signal:
        category = "human"
        machine_type = None
        importance = "medium"
        automation_safety = "low"
        confidence = 0.68
        reason = "Reply-style subject suggests a human conversation."
        suggested_actions = ["review"]
    else:
        category = "needs_review"
        machine_type = None
        importance = "medium"
        automation_safety = "low"
        confidence = 0.55
        reason = "No strong human or machine signal."
        suggested_actions = ["review"]

    return ClassificationRecord(
        message_id=message.id,
        category=category,
        machine_type=machine_type,
        importance=importance,
        automation_safety=automation_safety,
        confidence=confidence,
        reason=reason,
        suggested_actions=suggested_actions,
        classifier_version=CLASSIFIER_VERSION,
    )


def _machine_score(sender_address: str, subject: str, text: str) -> int:
    score = 0
    if _contains_any(sender_address, MACHINE_SENDER_TERMS):
        score += 2
    if _contains_any(subject.lower(), MACHINE_SUBJECT_TERMS):
        score += 1
    if re.search(r"\b(order|receipt|invoice|statement)[ #:]?\w+", text):
        score += 1
    return score


def _machine_type(text: str) -> str | None:
    if _contains_any(text, ("newsletter", "unsubscribe")):
        return "newsletter"
    if _contains_any(text, ("delivered", "delivery", "shipped", "tracking")):
        return "delivery"
    if _contains_any(text, ("receipt", "invoice", "statement", "payment")):
        return "transactional"
    if _contains_any(text, ("security", "password", "verification code", "account recovery")):
        return "security"
    return "notification"


def _is_github_copilot_notification(sender_address: str, text: str) -> bool:
    return sender_address == "notifications@github.com" and _contains_any(
        text,
        (
            "copilot",
            "copilot-pull-request-reviewer",
        ),
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9 ]+", term):
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return term in text
