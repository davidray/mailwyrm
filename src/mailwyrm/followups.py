from __future__ import annotations

from datetime import UTC, datetime

from mailwyrm.models import FollowUpMarker
from mailwyrm.store import MailwyrmState


def set_followup(
    state: MailwyrmState,
    *,
    message_ids: list[str],
    followup: bool,
    reason: str = "",
) -> dict[str, int]:
    unique_message_ids = list(dict.fromkeys(message_ids))
    if not unique_message_ids:
        raise ValueError("message_ids is required")
    missing = [message_id for message_id in unique_message_ids if message_id not in state.messages]
    if missing:
        raise ValueError(f"message is not in the local index: {missing[0]}")

    changed = 0
    if followup:
        created_at = datetime.now(UTC).isoformat()
        for message_id in unique_message_ids:
            if message_id in state.followups:
                continue
            state.followups[message_id] = FollowUpMarker(
                message_id=message_id,
                reason=reason,
                created_at=created_at,
            )
            changed += 1
    else:
        for message_id in unique_message_ids:
            if state.followups.pop(message_id, None) is not None:
                changed += 1

    return {
        "changed": changed,
        "marked": sum(1 for message_id in unique_message_ids if message_id in state.followups),
        "total": len(unique_message_ids),
    }


def message_needs_followup(state: MailwyrmState, message_id: str) -> bool:
    return message_id in state.followups
