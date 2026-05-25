from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from mailwyrm.models import ClassificationRecord, MessageRecord
from mailwyrm.store import MailwyrmState


DIGEST_SECTION_ORDER = (
    "transactional",
    "delivery",
    "newsletter",
    "security",
    "notification",
    "needs_review",
)


@dataclass(frozen=True)
class DigestItem:
    message: MessageRecord
    classification: ClassificationRecord


def render_digest(state: MailwyrmState, *, title_date: str | None = None) -> str:
    title_date = title_date or datetime.now(UTC).date().isoformat()
    items = _digest_items(state)
    lines = [
        f"# Mailwyrm Machine Digest - {title_date}",
        "",
        f"Account: {state.account_email or 'unknown'}",
        f"Items: {len(items)}",
        "",
    ]

    if not items:
        lines.extend(
            [
                "No machine or high-importance review items are ready for the digest.",
                "",
            ]
        )
        return "\n".join(lines)

    grouped: dict[str, list[DigestItem]] = defaultdict(list)
    for item in items:
        grouped[_section_for(item.classification)].append(item)

    for section in DIGEST_SECTION_ORDER:
        section_items = grouped.get(section, [])
        if not section_items:
            continue
        lines.extend([f"## {_section_title(section)}", ""])
        for item in section_items:
            lines.extend(_render_item(item))
        lines.append("")

    return "\n".join(lines)


def _digest_items(state: MailwyrmState) -> list[DigestItem]:
    items: list[DigestItem] = []
    for message in sorted(
        state.messages.values(),
        key=lambda record: record.internal_date or "",
        reverse=True,
    ):
        classification = state.classifications.get(message.id)
        if not classification:
            continue
        if classification.category == "machine" or (
            classification.category == "needs_review"
            and classification.importance == "high"
        ):
            items.append(DigestItem(message=message, classification=classification))
    return items


def _section_for(classification: ClassificationRecord) -> str:
    if classification.category == "needs_review":
        return "needs_review"
    return classification.machine_type or "notification"


def _section_title(section: str) -> str:
    return {
        "transactional": "Transactional",
        "delivery": "Deliveries",
        "newsletter": "Newsletters",
        "security": "Security And Account",
        "notification": "Notifications",
        "needs_review": "Needs Review",
    }[section]


def _render_item(item: DigestItem) -> list[str]:
    message = item.message
    classification = item.classification
    sender = _escape_markdown(_single_line(message.headers.get("From", "(unknown sender)")))
    subject = _escape_markdown(_single_line(message.headers.get("Subject", "(no subject)")))
    gmail_url = f"https://mail.google.com/mail/u/0/#inbox/{message.id}"
    snippet = _escape_markdown(_clean_snippet(message.snippet))
    reason = _escape_markdown(_single_line(classification.reason))

    lines = [
        f"- [{subject}]({gmail_url})",
        f"  From: {sender}",
        (
            "  "
            f"Importance: {classification.importance}; "
            f"automation safety: {classification.automation_safety}; "
            f"confidence: {classification.confidence:.2f}"
        ),
        f"  Reason: {reason}",
    ]
    if snippet:
        lines.append(f"  Snippet: {snippet}")
    return lines


def _clean_snippet(snippet: str) -> str:
    normalized = _single_line(snippet)
    if len(normalized) <= 220:
        return normalized
    return f"{normalized[:217]}..."


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _escape_markdown(text: str) -> str:
    replacements = {
        "\\": "\\\\",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "#": "\\#",
        "|": "\\|",
        "<": "\\<",
        ">": "\\>",
    }
    return "".join(replacements.get(character, character) for character in text)
