from __future__ import annotations

from dataclasses import replace

from mailwyrm.models import (
    CLASSIFICATION_CATEGORIES,
    MACHINE_TYPES,
    ClassificationCorrection,
    ClassificationRecord,
)
from mailwyrm.store import MailwyrmState


class CorrectionError(ValueError):
    pass


def add_correction(
    state: MailwyrmState,
    *,
    message_id: str,
    category: str,
    machine_type: str | None = None,
    reason: str = "",
) -> ClassificationCorrection:
    if message_id not in state.messages:
        raise CorrectionError(f"message {message_id} is not in the local index")
    if category not in CLASSIFICATION_CATEGORIES:
        raise CorrectionError(
            f"category must be one of: {', '.join(CLASSIFICATION_CATEGORIES)}"
        )
    if category != "machine" and machine_type is not None:
        raise CorrectionError("machine_type can only be set for machine corrections")
    if category == "machine" and machine_type is None:
        machine_type = "transactional"
    if category == "machine" and machine_type not in MACHINE_TYPES:
        raise CorrectionError(
            f"machine_type must be one of: {', '.join(MACHINE_TYPES)}"
        )

    correction = ClassificationCorrection(
        message_id=message_id,
        category=category,
        machine_type=machine_type,
        reason=reason,
    )
    state.corrections[message_id] = correction
    return correction


def effective_classification(
    classification: ClassificationRecord,
    correction: ClassificationCorrection | None,
) -> ClassificationRecord:
    if correction is None:
        return classification

    return replace(
        classification,
        category=correction.category,
        machine_type=correction.machine_type,
        confidence=1.0,
        reason=correction.reason or f"User corrected classification to {correction.category}.",
        suggested_actions=_suggested_actions(correction.category),
        classifier_version=f"{classification.classifier_version}+user-correction",
    )


def correction_report(state: MailwyrmState) -> str:
    total = len(state.corrections)
    changed = 0
    lines = [f"Corrections: {total}"]
    for message_id, correction in sorted(state.corrections.items()):
        original = state.classifications.get(message_id)
        if original and original.category != correction.category:
            changed += 1
        message = state.messages.get(message_id)
        subject = "(missing message)" if message is None else message.headers.get(
            "Subject",
            "(no subject)",
        )
        lines.append(f"- {message_id}\t{correction.category}\t{subject}")

    lines.insert(1, f"Category changes: {changed}")
    return "\n".join(lines)


def _suggested_actions(category: str) -> list[str]:
    if category == "machine":
        return ["digest"]
    return ["review"]
