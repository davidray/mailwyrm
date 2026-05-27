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
    suggested_actions: list[str] | None = None,
    importance: str | None = None,
    automation_safety: str | None = None,
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
    suggested_actions = _validated_suggested_actions(suggested_actions)
    if importance is not None and importance not in {"low", "medium", "high"}:
        raise CorrectionError("importance must be one of: low, medium, high")
    if automation_safety is not None and automation_safety not in {"low", "medium", "high"}:
        raise CorrectionError("automation_safety must be one of: low, medium, high")

    correction = ClassificationCorrection(
        message_id=message_id,
        category=category,
        machine_type=machine_type,
        reason=reason,
        suggested_actions=suggested_actions,
        importance=importance,
        automation_safety=automation_safety,
    )
    state.corrections[message_id] = correction
    return correction


def add_review_resolution(
    state: MailwyrmState,
    *,
    message_id: str,
    resolution: str,
    machine_type: str | None = None,
    reason: str = "",
) -> ClassificationCorrection:
    if resolution == "human":
        return add_correction(
            state,
            message_id=message_id,
            category="human",
            reason=reason or "User resolved review item as human correspondence.",
            suggested_actions=[],
            importance="medium",
            automation_safety="low",
        )
    if resolution == "protect":
        return add_correction(
            state,
            message_id=message_id,
            category="needs_review",
            reason=reason or "User protected this message from mailbox automation.",
            suggested_actions=["review", "protect"],
            importance="high",
            automation_safety="low",
        )
    if resolution == "machine":
        machine_type = machine_type or "transactional"
        return add_correction(
            state,
            message_id=message_id,
            category="machine",
            machine_type=machine_type,
            reason=(
                reason
                or f"User resolved review item as {machine_type.replace('_', ' ')} mail."
            ),
            suggested_actions=_machine_review_actions(machine_type),
            importance=_machine_importance(machine_type),
            automation_safety=_machine_safety(machine_type),
        )
    if resolution == "archive":
        if machine_type is None:
            raise CorrectionError("archive resolution requires machine_type")
        return add_correction(
            state,
            message_id=message_id,
            category="machine",
            machine_type=machine_type,
            reason=reason or "User resolved review item as machine mail to archive after digest.",
            suggested_actions=["digest", "archive"],
            importance=_machine_importance(machine_type),
            automation_safety=_machine_safety(machine_type),
        )
    if resolution == "trash":
        return add_correction(
            state,
            message_id=message_id,
            category="machine",
            machine_type=machine_type or "spam",
            reason=reason or "User resolved review item as low-risk machine mail to trash after digest.",
            suggested_actions=["digest", "trash"],
            importance="low",
            automation_safety="high",
        )
    raise CorrectionError(
        "resolution must be one of: human, machine, protect, archive, trash"
    )


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
        review_type=None,
        importance=correction.importance or _effective_importance(correction),
        automation_safety=(
            correction.automation_safety or _effective_automation_safety(correction)
        ),
        confidence=1.0,
        reason=correction.reason or f"User corrected classification to {correction.category}.",
        suggested_actions=(
            correction.suggested_actions
            if correction.suggested_actions is not None
            else _suggested_actions(correction.category)
        ),
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
        return ["digest", "archive"]
    if category == "human":
        return []
    return ["review"]


def _machine_review_actions(machine_type: str | None) -> list[str]:
    if machine_type == "spam":
        return ["digest", "trash"]
    return ["digest"]


def _validated_suggested_actions(actions: list[str] | None) -> list[str] | None:
    if actions is None:
        return None
    actions = [str(action) for action in actions]
    allowed = {"label", "archive", "digest", "trash", "protect", "review"}
    invalid = sorted(set(actions) - allowed)
    if invalid:
        raise CorrectionError(
            f"suggested_actions contains unsupported action(s): {', '.join(invalid)}"
        )
    return actions


def _effective_importance(correction: ClassificationCorrection) -> str:
    if correction.category == "machine":
        return _machine_importance(correction.machine_type)
    if correction.category == "human":
        return "medium"
    return "high" if "protect" in (correction.suggested_actions or []) else "medium"


def _effective_automation_safety(correction: ClassificationCorrection) -> str:
    if correction.category == "machine":
        return _machine_safety(correction.machine_type)
    return "low"


def _machine_importance(machine_type: str | None) -> str:
    if machine_type in {"marketing", "spam", "product_community"}:
        return "low"
    return "medium"


def _machine_safety(machine_type: str | None) -> str:
    if machine_type in {"marketing", "spam", "product_community"}:
        return "high"
    return "medium"
