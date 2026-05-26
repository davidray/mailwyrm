from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from mailwyrm.store import MailwyrmState
from mailwyrm.corrections import effective_classification
from mailwyrm.models import (
    ClassificationRecord,
    DigestAuditEvent,
    MACHINE_TYPES,
    MessageRecord,
)


DIGEST_SECTION_ORDER = (
    *MACHINE_TYPES,
    "needs_review",
)


@dataclass(frozen=True)
class DigestItem:
    message: MessageRecord
    classification: ClassificationRecord


def render_digest(
    state: MailwyrmState,
    *,
    title_date: str | None = None,
    limit: int | None = None,
) -> str:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    title_date = title_date or datetime.now(UTC).date().isoformat()
    all_items = _digest_items(state)
    items = all_items
    if limit is not None:
        items = items[:limit]
    lines = [
        f"# Mailwyrm Machine Digest - {title_date}",
        "",
        f"Account: {state.account_email or 'unknown'}",
        f"Items: {len(items)}",
        "",
    ]

    if not items:
        empty_message = (
            "No digest items are shown because the limit is 0."
            if all_items
            else "No machine or high-importance review items are ready for the digest."
        )
        lines.extend(
            [
                empty_message,
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


def mark_digest_items(
    state: MailwyrmState,
    *,
    title_date: str | None = None,
) -> int:
    title_date = title_date or datetime.now(UTC).date().isoformat()
    items = _digest_items(state)
    existing_message_ids = {
        event.message_id
        for event in state.digest_audit_events
        if event.digest_title_date == title_date
    }
    marked = 0
    for item in items:
        if item.message.id in existing_message_ids:
            continue
        state.digest_audit_events.append(
            DigestAuditEvent(
                message_id=item.message.id,
                digest_title_date=title_date,
                reason=item.classification.reason,
                classifier_version=item.classification.classifier_version,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        marked += 1
    return marked


def message_has_been_digested(state: MailwyrmState, message_id: str) -> bool:
    return any(event.message_id == message_id for event in state.digest_audit_events)


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
        classification = effective_classification(
            classification,
            state.corrections.get(message.id),
        )
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
