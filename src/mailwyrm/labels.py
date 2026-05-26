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
DIGESTED_LABEL = "Mailwyrm/Digested"
PROTECTED_LABEL = "Mailwyrm/Protected"


@dataclass(frozen=True)
class LabelPlan:
    message: MessageRecord
    classification: ClassificationRecord
    label_names: list[str]


@dataclass(frozen=True)
class DigestedLabelPlan:
    message: MessageRecord
    label_name: str
    reason: str
    classifier_version: str


def build_label_plans(
    state: MailwyrmState,
    *,
    limit: int | None = None,
    mailbox: str = "inbox",
) -> list[LabelPlan]:
    if limit == 0:
        return []

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


def build_digested_label_plans(
    state: MailwyrmState,
    *,
    limit: int | None = None,
) -> list[DigestedLabelPlan]:
    if limit == 0:
        return []

    plans: list[DigestedLabelPlan] = []
    seen_message_ids: set[str] = set()
    for event in reversed(state.digest_audit_events):
        if event.message_id in seen_message_ids:
            continue
        seen_message_ids.add(event.message_id)
        message = state.messages.get(event.message_id)
        if message is None:
            continue
        plans.append(
            DigestedLabelPlan(
                message=message,
                label_name=DIGESTED_LABEL,
                reason=event.reason,
                classifier_version=event.classifier_version,
            )
        )
        if limit is not None and len(plans) >= limit:
            break
    return plans


def _message_matches_mailbox(message: MessageRecord, mailbox: str) -> bool:
    if mailbox == "all-mail":
        return True
    label_ids = set(message.label_ids)
    if mailbox == "trash":
        return "TRASH" in label_ids
    return "INBOX" in label_ids


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


def render_digested_label_preview(plans: list[DigestedLabelPlan]) -> str:
    if not plans:
        return "No digested messages are ready for Gmail labels."
    lines = ["Message ID\tLabels\tSubject"]
    for plan in plans:
        subject = plan.message.headers.get("Subject", "(no subject)")
        lines.append(f"{plan.message.id}\t{plan.label_name}\t{subject}")
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


def apply_digested_label_plans(
    client: GmailClient,
    state: MailwyrmState,
    plans: list[DigestedLabelPlan],
) -> int:
    if not plans:
        return 0

    labels_by_name = client.ensure_mailwyrm_labels((DIGESTED_LABEL,))
    digested_label = labels_by_name[DIGESTED_LABEL]
    applied = 0
    for plan in plans:
        if digested_label.id in plan.message.label_ids:
            continue

        client.add_labels_to_message(plan.message.id, [digested_label.id])
        state.messages[plan.message.id] = replace(
            plan.message,
            label_ids=[*plan.message.label_ids, digested_label.id],
        )
        state.label_audit_events.append(
            LabelAuditEvent(
                message_id=plan.message.id,
                action="add_digested_label",
                label_names=[DIGESTED_LABEL],
                label_ids=[digested_label.id],
                reason=plan.reason,
                classifier_version=plan.classifier_version,
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
