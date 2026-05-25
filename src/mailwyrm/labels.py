from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from mailwyrm.corrections import effective_classification
from mailwyrm.gmail import GmailClient, GmailLabel
from mailwyrm.models import (
    ClassificationRecord,
    LabelAuditEvent,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState


CATEGORY_LABELS = {
    "human": "Mailwyrm/Human",
    "machine": "Mailwyrm/Machine",
    "needs_review": "Mailwyrm/Needs Review",
}
PROTECTED_LABEL = "Mailwyrm/Protected"


@dataclass(frozen=True)
class LabelPlan:
    message: MessageRecord
    classification: ClassificationRecord
    label_names: list[str]


def build_label_plans(
    state: MailwyrmState,
    *,
    limit: int | None = None,
    mailbox: str = "inbox",
) -> list[LabelPlan]:
    plans: list[LabelPlan] = []
    messages = sorted(
        state.messages.values(),
        key=lambda message: message.internal_date or "",
        reverse=True,
    )
    for message in messages:
        if not _message_matches_mailbox(message, mailbox):
            continue
        classification = state.classifications.get(message.id)
        if not classification:
            continue
        classification = effective_classification(
            classification,
            state.corrections.get(message.id),
        )
        label_names = labels_for_classification(classification)
        if label_names:
            plans.append(
                LabelPlan(
                    message=message,
                    classification=classification,
                    label_names=label_names,
                )
            )
        if limit is not None and len(plans) >= limit:
            break
    return plans


def _message_matches_mailbox(message: MessageRecord, mailbox: str) -> bool:
    if mailbox == "all-mail":
        return True
    return "INBOX" in message.label_ids


def labels_for_classification(classification: ClassificationRecord) -> list[str]:
    label_name = CATEGORY_LABELS.get(classification.category)
    if label_name is None:
        return []
    label_names = [label_name]
    if _is_protected(classification):
        label_names.append(PROTECTED_LABEL)
    return label_names


def render_label_preview(plans: list[LabelPlan]) -> str:
    if not plans:
        return "No classified messages are ready for Gmail labels."
    lines = ["Message ID\tLabels\tSubject"]
    for plan in plans:
        subject = plan.message.headers.get("Subject", "(no subject)")
        lines.append(
            f"{plan.message.id}\t{', '.join(plan.label_names)}\t{subject}"
        )
    return "\n".join(lines)


def apply_label_plans(
    client: GmailClient,
    state: MailwyrmState,
    plans: list[LabelPlan],
) -> int:
    if not plans:
        return 0

    labels_by_name = client.ensure_mailwyrm_labels()
    applied = 0
    for plan in plans:
        message_label_ids = set(plan.message.label_ids)
        missing_labels = [
            (label_name, labels_by_name[label_name].id)
            for label_name in plan.label_names
            if labels_by_name[label_name].id not in message_label_ids
        ]
        if not missing_labels:
            continue

        missing_label_names = [label_name for label_name, _label_id in missing_labels]
        missing_label_ids = [label_id for _label_name, label_id in missing_labels]
        client.add_labels_to_message(plan.message.id, missing_label_ids)
        state.messages[plan.message.id] = replace(
            plan.message,
            label_ids=[*plan.message.label_ids, *missing_label_ids],
        )
        state.label_audit_events.append(
            LabelAuditEvent(
                message_id=plan.message.id,
                action="add_labels",
                label_names=missing_label_names,
                label_ids=missing_label_ids,
                reason=plan.classification.reason,
                classifier_version=plan.classification.classifier_version,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        applied += 1
    return applied


def _is_protected(classification: ClassificationRecord) -> bool:
    return (
        classification.category == "needs_review"
        and (
            classification.importance == "high"
            or "protect" in classification.suggested_actions
        )
    )
