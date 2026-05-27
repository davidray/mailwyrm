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

FINANCE_REVIEW_TERMS = (
    "bank",
    "card",
    "fraud",
    "invoice",
    "payment",
    "tax",
)

LEGAL_REVIEW_TERMS = ("legal", "lawsuit", "contract", "court")
MEDICAL_REVIEW_TERMS = ("medical", "health", "doctor", "clinic", "insurance")
SECURITY_REVIEW_TERMS = ("security", "verification code")
ACCOUNT_ACCESS_REVIEW_TERMS = (
    "account recovery",
    "password",
    "reset your password",
    "sign-in",
    "login",
)
TRAVEL_REVIEW_TERMS = (
    "flight",
    "hotel",
    "reservation",
    "boarding",
    "itinerary",
    "travel",
)

MACHINE_SENDER_TERMS = (
    "alert",
    "billing",
    "bounce",
    "community",
    "delivery",
    "do-not-reply",
    "donotreply",
    "forum",
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
    "digest",
    "discussion",
    "invoice",
    "newsletter",
    "order",
    "promo",
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
    text = " ".join([sender, subject, message.snippet, message.body_text]).lower()
    sender_address = parseaddr(sender)[1].lower()

    high_risk = _contains_any(text, HIGH_RISK_TERMS)
    machine_score = _machine_score(sender_address, subject, text)
    human_reply_signal = subject.strip().lower().startswith(HUMAN_REPLY_PREFIXES)

    if high_risk:
        category = "needs_review"
        machine_type = None
        review_type = _review_type(text, human_reply_signal=human_reply_signal)
        importance = "high"
        automation_safety = "low"
        confidence = 0.74
        reason = "High-risk account, payment, security, legal, medical, or similar topic."
        suggested_actions = ["review", "protect"]
    elif _is_github_copilot_notification(sender_address, text):
        category = "machine"
        machine_type = "product_community"
        review_type = None
        importance = "low"
        automation_safety = "high"
        confidence = 0.94
        reason = "Low-risk Copilot notification from GitHub."
        suggested_actions = ["digest", "trash"]
    elif machine_score >= 2 and not human_reply_signal:
        category = "machine"
        machine_type = _machine_type(text)
        review_type = None
        importance = "medium" if machine_type == "transactional" else "low"
        automation_safety = "high" if machine_type == "spam" else "medium"
        confidence = min(0.95, 0.62 + (machine_score * 0.1))
        reason = "Automated sender or subject pattern."
        suggested_actions = ["digest", "trash"] if machine_type == "spam" else ["digest"]
    elif human_reply_signal:
        category = "human"
        machine_type = None
        review_type = None
        importance = "medium"
        automation_safety = "low"
        confidence = 0.68
        reason = "Reply-style subject suggests a human conversation."
        suggested_actions = ["review"]
    else:
        category = "needs_review"
        machine_type = None
        review_type = _review_type(text, human_reply_signal=human_reply_signal)
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
        review_type=review_type,
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
    if _contains_any(
        text,
        (
            "winner",
            "lottery",
            "crypto giveaway",
            "limited time prize",
            "act now",
            "free money",
        ),
    ):
        return "spam"
    if _contains_any(
        text,
        (
            "receipt",
            "invoice",
            "statement",
            "payment",
            "delivered",
            "delivery",
            "shipped",
            "tracking",
            "order",
            "renewal",
            "subscription",
        ),
    ):
        return "transactional"
    if _contains_any(
        text,
        (
            "community",
            "discussion",
            "forum",
            "github",
            "pull request",
            "issue",
            "commented",
        ),
    ):
        return "product_community"
    if _contains_any(text, ("newsletter", "news", "weekly digest", "daily digest")):
        return "news"
    if _contains_any(
        text,
        (
            "unsubscribe",
            "marketing",
            "promo",
            "promotion",
            "sale",
            "discount",
            "deal",
            "offer",
        ),
    ):
        return "marketing"
    return "transactional"


def _review_type(text: str, *, human_reply_signal: bool) -> str:
    if human_reply_signal:
        return "possible_human"
    if _contains_any(text, ACCOUNT_ACCESS_REVIEW_TERMS):
        return "account_access"
    if _contains_any(text, SECURITY_REVIEW_TERMS):
        return "security"
    if _contains_any(text, FINANCE_REVIEW_TERMS):
        return "finance"
    if _contains_any(text, LEGAL_REVIEW_TERMS):
        return "legal"
    if _contains_any(text, MEDICAL_REVIEW_TERMS):
        return "medical"
    if _contains_any(text, TRAVEL_REVIEW_TERMS):
        return "travel"
    if _contains_any(text, MACHINE_SENDER_TERMS + MACHINE_SUBJECT_TERMS):
        return "uncertain_machine"
    return "unknown"


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
