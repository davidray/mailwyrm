from __future__ import annotations

from dataclasses import dataclass

from mailwyrm.corrections import effective_classification
from mailwyrm.models import ClassificationRecord, MessageRecord
from mailwyrm.store import MailwyrmState


ACTION_KEEP = "keep"
ACTION_REVIEW = "review"
ACTION_PROTECT = "protect"
ACTION_ARCHIVE_AFTER_DIGEST = "archive_after_digest"
ACTION_TRASH_AFTER_DIGEST = "trash_after_digest"


@dataclass(frozen=True)
class ActionPlan:
    message: MessageRecord
    classification: ClassificationRecord
    action: str
    reason: str


def build_action_plans(
    state: MailwyrmState,
    *,
    limit: int | None = None,
    mailbox: str = "inbox",
) -> list[ActionPlan]:
    plans: list[ActionPlan] = []
    messages = sorted(
        state.messages.values(),
        key=lambda message: message.internal_date or "",
        reverse=True,
    )
    for message in messages:
        if not _message_matches_mailbox(message, mailbox):
            continue
        classification = state.classifications.get(message.id)
        if classification is None:
            continue
        classification = effective_classification(
            classification,
            state.corrections.get(message.id),
        )
        plans.append(plan_action(message, classification))
        if limit is not None and len(plans) >= limit:
            break
    return plans


def plan_action(
    message: MessageRecord,
    classification: ClassificationRecord,
) -> ActionPlan:
    if classification.category == "human":
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_KEEP,
            reason="Human correspondence should stay foregrounded.",
        )

    if _is_protected(classification):
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_PROTECT,
            reason="High-risk or important mail is protected from automation.",
        )

    if classification.category == "needs_review":
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_REVIEW,
            reason="Classification needs review before mailbox automation.",
        )

    if classification.confidence < 0.75:
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_REVIEW,
            reason="Classifier confidence is too low for mailbox automation.",
        )

    if _can_trash_after_digest(classification):
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_TRASH_AFTER_DIGEST,
            reason="Low-importance machine mail could be trashed after digest under approved policy.",
        )

    if classification.category == "machine":
        return ActionPlan(
            message=message,
            classification=classification,
            action=ACTION_ARCHIVE_AFTER_DIGEST,
            reason="Machine mail can leave the inbox after digest under approved policy.",
        )

    return ActionPlan(
        message=message,
        classification=classification,
        action=ACTION_REVIEW,
        reason="Unknown classification category.",
    )


def render_action_preview(plans: list[ActionPlan]) -> str:
    if not plans:
        return "No classified messages are ready for mailbox action preview."

    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.action] = counts.get(plan.action, 0) + 1

    lines = [
        "Mailbox Action Preview",
        "No Gmail actions will be performed.",
        "",
        "Action counts:",
    ]
    for action in sorted(counts):
        lines.append(f"- {action}: {counts[action]}")
    lines.extend(["", "Message ID\tAction\tCategory\tConfidence\tSubject\tReason"])

    for plan in plans:
        subject = _table_field(plan.message.headers.get("Subject", "(no subject)"))
        reason = _table_field(plan.reason)
        lines.append(
            "\t".join(
                [
                    plan.message.id,
                    plan.action,
                    plan.classification.category,
                    f"{plan.classification.confidence:.2f}",
                    subject,
                    reason,
                ]
            )
        )
    return "\n".join(lines)


def _can_trash_after_digest(classification: ClassificationRecord) -> bool:
    return (
        classification.category == "machine"
        and classification.importance == "low"
        and classification.automation_safety == "high"
        and classification.confidence >= 0.9
        and "trash" in classification.suggested_actions
    )


def _is_protected(classification: ClassificationRecord) -> bool:
    return (
        classification.importance == "high"
        or classification.automation_safety == "low"
        or "protect" in classification.suggested_actions
    )


def _message_matches_mailbox(message: MessageRecord, mailbox: str) -> bool:
    if mailbox == "all-mail":
        return True
    return "INBOX" in message.label_ids


def _table_field(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())
