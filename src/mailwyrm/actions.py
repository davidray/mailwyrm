from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from mailwyrm.corrections import effective_classification
from mailwyrm.gmail import GmailClient
from mailwyrm.models import ClassificationRecord, LabelAuditEvent, MessageRecord
from mailwyrm.store import MailwyrmState


ACTION_KEEP = "keep"
ACTION_REVIEW = "review"
ACTION_PROTECT = "protect"
ACTION_ARCHIVE_AFTER_DIGEST = "archive_after_digest"
ACTION_RESTORE_ARCHIVE = "restore_archive"
ACTION_TRASH_AFTER_DIGEST = "trash_after_digest"
GMAIL_INBOX_LABEL = "INBOX"


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
    if limit == 0:
        return []

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


def render_action_preview(
    plans: list[ActionPlan],
    *,
    mutates_gmail: bool = False,
) -> str:
    if not plans:
        return "No classified messages are ready for mailbox action preview."

    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.action] = counts.get(plan.action, 0) + 1

    lines = ["Mailbox Action Preview", _mutation_notice(mutates_gmail), "", "Action counts:"]
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


def apply_archive_action_plans(
    client: GmailClient,
    state: MailwyrmState,
    plans: list[ActionPlan],
) -> int:
    applied = 0
    for plan in plans:
        if plan.action != ACTION_ARCHIVE_AFTER_DIGEST:
            continue
        if GMAIL_INBOX_LABEL not in plan.message.label_ids:
            continue

        client.remove_labels_from_message(plan.message.id, [GMAIL_INBOX_LABEL])
        state.messages[plan.message.id] = replace(
            plan.message,
            label_ids=[
                label_id
                for label_id in plan.message.label_ids
                if label_id != GMAIL_INBOX_LABEL
            ],
        )
        state.label_audit_events.append(
            LabelAuditEvent(
                message_id=plan.message.id,
                action=ACTION_ARCHIVE_AFTER_DIGEST,
                label_names=[GMAIL_INBOX_LABEL],
                label_ids=[GMAIL_INBOX_LABEL],
                reason=plan.classification.reason,
                classifier_version=plan.classification.classifier_version,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        applied += 1
    return applied


def restore_archived_message(
    client: GmailClient,
    state: MailwyrmState,
    message_id: str,
) -> bool:
    message = state.messages.get(message_id)
    if message is None:
        raise ValueError(f"message {message_id} is not in the local index")
    if GMAIL_INBOX_LABEL in message.label_ids:
        return False

    client.add_labels_to_message(message_id, [GMAIL_INBOX_LABEL])
    state.messages[message_id] = replace(
        message,
        label_ids=[*message.label_ids, GMAIL_INBOX_LABEL],
    )
    classification = state.classifications.get(message_id)
    state.label_audit_events.append(
        LabelAuditEvent(
            message_id=message_id,
            action=ACTION_RESTORE_ARCHIVE,
            label_names=[GMAIL_INBOX_LABEL],
            label_ids=[GMAIL_INBOX_LABEL],
            reason="User restored archived message to inbox.",
            classifier_version=(
                classification.classifier_version if classification else "manual"
            ),
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    return True


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
    return GMAIL_INBOX_LABEL in message.label_ids


def _table_field(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())


def _mutation_notice(mutates_gmail: bool) -> str:
    if mutates_gmail:
        return "Gmail will be modified after this preview."
    return "No Gmail actions will be performed."
