from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mailwyrm.actions import (
    ACTION_ARCHIVE_AFTER_DIGEST,
    ACTION_KEEP,
    ACTION_PROTECT,
    ACTION_REVIEW,
    ACTION_TRASH_AFTER_DIGEST,
    build_action_plans,
    build_trash_preview,
    message_matches_mailbox,
    plan_action,
)
from mailwyrm.corrections import effective_classification
from mailwyrm.digest import build_digest_items
from mailwyrm.store import MailwyrmState


SUPPORTED_MAILBOXES = ("inbox", "all-mail", "trash")


def build_daily_cockpit_payload(
    state: MailwyrmState,
    *,
    title_date: str | None = None,
    limit: int | None = 25,
    mailbox: str = "inbox",
    audit_limit: int = 10,
) -> dict[str, Any]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if audit_limit < 0:
        raise ValueError("audit_limit must be non-negative")
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError("mailbox must be one of inbox, all-mail, or trash")

    title_date = title_date or datetime.now(UTC).date().isoformat()
    action_plans = build_action_plans(state, limit=limit, mailbox=mailbox)
    trash_preview = build_trash_preview(state, limit=limit, mailbox=mailbox)
    all_digest_items = build_digest_items(state)
    digest_items = all_digest_items if limit is None else all_digest_items[:limit]
    attention_lanes = _attention_lanes(state, mailbox=mailbox, limit=limit)
    audit_events = sorted(
        state.label_audit_events,
        key=lambda event: event.created_at,
        reverse=True,
    )
    visible_audit_events = audit_events[:audit_limit]

    return {
        "title": "Mailwyrm Daily Cockpit",
        "date": title_date,
        "read_only": True,
        "account": {
            "email": state.account_email or "unknown",
            "last_sync_mailbox": state.last_sync_mailbox or "unknown",
            "indexed_messages": len(state.messages),
            "classified_messages": len(state.classifications),
        },
        "attention": {
            **_classification_counts(state),
            "actions": _action_counts(action_plans),
        },
        "policy": {
            "archive_after_digest": state.automation_policy.archive_after_digest_enabled,
            "trash_after_digest": state.automation_policy.trash_after_digest_enabled,
        },
        "lanes": attention_lanes,
        "digest": {
            "total_items": len(all_digest_items),
            "showing_items": len(digest_items),
            "items": [_digest_item_payload(item) for item in digest_items],
        },
        "mailbox_actions": {
            "mailbox": mailbox,
            "counts": _action_counts(action_plans),
            "plans": [_action_plan_payload(plan, mailbox=mailbox) for plan in action_plans],
        },
        "trash_gate": {
            "policy_enabled": trash_preview.policy_enabled,
            "skipped_policy_disabled": trash_preview.skipped_policy_disabled,
            "skipped_not_digested": trash_preview.skipped_not_digested,
            "skipped_already_trashed": trash_preview.skipped_already_trashed,
            "plans": [
                _action_plan_payload(plan, mailbox=mailbox)
                for plan in trash_preview.plans
            ],
        },
        "audit": {
            "total_events": len(audit_events),
            "showing_events": len(visible_audit_events),
            "events": [_audit_event_payload(state, event) for event in visible_audit_events],
        },
        "workflows": _workflow_controls(
            state=state,
            mailbox=mailbox,
            limit=limit,
            action_plans=action_plans,
            trash_preview=trash_preview,
            policy=state.automation_policy,
        ),
        "commands": [
            "uv run mailwyrm sync --mailbox inbox --limit 25 --client-secret /path/to/client_secret.json",
            "uv run mailwyrm classify",
            "uv run mailwyrm daily apply --limit 25 --client-secret /path/to/client_secret.json",
            "uv run mailwyrm actions apply-trash --limit 10 --client-secret /path/to/client_secret.json",
        ],
    }


def _classification_counts(state: MailwyrmState) -> dict[str, int]:
    counts = {"human": 0, "machine": 0, "needs_review": 0}
    for message_id, classification in state.classifications.items():
        classification = effective_classification(
            classification,
            state.corrections.get(message_id),
        )
        counts[classification.category] = counts.get(classification.category, 0) + 1
    return counts


def _action_counts(action_plans) -> dict[str, int]:
    counts = {
        ACTION_KEEP: 0,
        ACTION_PROTECT: 0,
        ACTION_REVIEW: 0,
        ACTION_ARCHIVE_AFTER_DIGEST: 0,
        ACTION_TRASH_AFTER_DIGEST: 0,
    }
    for plan in action_plans:
        counts[plan.action] = counts.get(plan.action, 0) + 1
    return counts


def _workflow_controls(
    *,
    state: MailwyrmState,
    mailbox: str,
    limit: int | None,
    action_plans,
    trash_preview,
    policy,
) -> list[dict[str, Any]]:
    limit_arg = "" if limit is None else f" --limit {limit}"
    mailbox_arg = f" --mailbox {mailbox}"
    action_counts = _action_counts(action_plans)
    archive_count = action_counts[ACTION_ARCHIVE_AFTER_DIGEST]
    trash_count = len(trash_preview.plans)
    label_count = len(action_plans)
    classify_count = _unclassified_message_count(state, mailbox=mailbox, limit=limit)

    return [
        {
            "id": "sync",
            "title": "Sync Gmail",
            "phase": "Read",
            "status": "Gmail read",
            "count": None,
            "mutates_gmail": False,
            "description": "Refresh the local index from Gmail for this mailbox scope.",
            "primary_command": (
                "uv run mailwyrm sync"
                f"{mailbox_arg}{limit_arg}"
                " --client-secret /path/to/client_secret.json"
            ),
        },
        {
            "id": "classify",
            "title": "Classify local mail",
            "phase": "AI",
            "status": "Local only",
            "count": classify_count,
            "mutates_gmail": False,
            "description": "Classify indexed messages before label or action previews.",
            "primary_command": f"uv run mailwyrm classify{mailbox_arg}{limit_arg}",
        },
        {
            "id": "daily-preview",
            "title": "Preview daily workflow",
            "phase": "Preview",
            "status": "No Gmail mutation",
            "count": label_count,
            "mutates_gmail": False,
            "description": "Render digest, labels, and mailbox action plans together.",
            "primary_command": (
                "uv run mailwyrm daily preview"
                f"{mailbox_arg}{limit_arg}"
            ),
        },
        {
            "id": "labels",
            "title": "Apply Gmail labels",
            "phase": "Visible labels",
            "status": "Mutates Gmail",
            "count": label_count,
            "mutates_gmail": True,
            "description": "Apply Gmail-visible Mailwyrm labels after reviewing the plan.",
            "preview_command": (
                "uv run mailwyrm labels preview"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm labels apply"
                f"{mailbox_arg}{limit_arg}"
                " --client-secret /path/to/client_secret.json"
            ),
        },
        {
            "id": "archive",
            "title": "Archive after digest",
            "phase": "Mailbox action",
            "status": "Mutates Gmail",
            "count": archive_count,
            "mutates_gmail": True,
            "description": "Archive eligible machine mail that already appeared in a digest.",
            "preview_command": (
                "uv run mailwyrm actions preview"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm actions apply-archive"
                f"{mailbox_arg}{limit_arg}"
                " --client-secret /path/to/client_secret.json"
            ),
        },
        {
            "id": "trash",
            "title": "Trash after digest",
            "phase": "Policy gate",
            "status": (
                "Policy enabled"
                if policy.trash_after_digest_enabled
                else "Policy disabled"
            ),
            "count": trash_count,
            "mutates_gmail": True,
            "description": "Move only policy-gated low-risk digest mail to Gmail Trash.",
            "preview_command": (
                "uv run mailwyrm actions preview-trash"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm actions apply-trash"
                f"{mailbox_arg}{limit_arg}"
                " --client-secret /path/to/client_secret.json"
            ),
        },
    ]


def _unclassified_message_count(
    state: MailwyrmState,
    *,
    mailbox: str,
    limit: int | None,
) -> int:
    count = 0
    selected = 0
    for message in sorted(
        state.messages.values(),
        key=lambda record: record.internal_date or "",
        reverse=True,
    ):
        if not message_matches_mailbox(message, mailbox):
            continue
        selected += 1
        if message.id not in state.classifications:
            count += 1
        if limit is not None and selected >= limit:
            break
    return count


def _attention_lanes(
    state: MailwyrmState,
    *,
    mailbox: str,
    limit: int | None,
) -> dict[str, Any]:
    lanes = {
        "human": {
            "total_items": 0,
            "showing_items": 0,
            "items": [],
        },
        "needs_review": {
            "total_items": 0,
            "showing_items": 0,
            "items": [],
        },
    }
    for message in sorted(
        state.messages.values(),
        key=lambda record: record.internal_date or "",
        reverse=True,
    ):
        if not message_matches_mailbox(message, mailbox):
            continue
        classification = state.classifications.get(message.id)
        if classification is None:
            continue
        classification = effective_classification(
            classification,
            state.corrections.get(message.id),
        )
        plan = plan_action(message, classification)
        lane_name = _lane_name(classification.category, plan.action)
        if lane_name is None:
            continue

        lane = lanes[lane_name]
        lane["total_items"] += 1
        if limit is None or lane["showing_items"] < limit:
            lane["items"].append(
                _lane_item_payload(
                    message,
                    classification,
                    action=plan.action,
                    reason=plan.reason,
                    mailbox=mailbox,
                )
            )
            lane["showing_items"] += 1
    return lanes


def _lane_name(category: str, action: str) -> str | None:
    if category == "human":
        return "human"
    if action in {ACTION_PROTECT, ACTION_REVIEW}:
        return "needs_review"
    return None


def _digest_item_payload(item) -> dict[str, Any]:
    message = item.message
    classification = item.classification
    return {
        "message_id": message.id,
        "thread_id": message.thread_id,
        "gmail_url": _gmail_url(message.id),
        "subject": _header(message, "Subject", "(no subject)"),
        "sender": _header(message, "From", "(unknown sender)"),
        "snippet": _clean_snippet(message.snippet),
        "category": classification.category,
        "machine_type": classification.machine_type,
        "importance": classification.importance,
        "automation_safety": classification.automation_safety,
        "confidence": classification.confidence,
        "reason": classification.reason,
    }


def _lane_item_payload(
    message,
    classification,
    *,
    action: str,
    reason: str,
    mailbox: str,
) -> dict[str, Any]:
    return {
        "message_id": message.id,
        "thread_id": message.thread_id,
        "gmail_url": _gmail_url(message.id, mailbox=mailbox),
        "subject": _header(message, "Subject", "(no subject)"),
        "sender": _header(message, "From", "(unknown sender)"),
        "snippet": _clean_snippet(message.snippet),
        "category": classification.category,
        "machine_type": classification.machine_type,
        "importance": classification.importance,
        "automation_safety": classification.automation_safety,
        "confidence": classification.confidence,
        "action": action,
        "reason": reason,
    }


def _action_plan_payload(plan, *, mailbox: str) -> dict[str, Any]:
    return {
        "message_id": plan.message.id,
        "thread_id": plan.message.thread_id,
        "gmail_url": _gmail_url(plan.message.id, mailbox=mailbox),
        "subject": _header(plan.message, "Subject", "(no subject)"),
        "sender": _header(plan.message, "From", "(unknown sender)"),
        "category": plan.classification.category,
        "machine_type": plan.classification.machine_type,
        "confidence": plan.classification.confidence,
        "action": plan.action,
        "reason": plan.reason,
    }


def _audit_event_payload(state: MailwyrmState, event) -> dict[str, Any]:
    message = state.messages.get(event.message_id)
    return {
        "created_at": event.created_at,
        "message_id": event.message_id,
        "gmail_url": _gmail_url(event.message_id),
        "action": event.action,
        "label_names": event.label_names,
        "subject": _header(message, "Subject", "(message not in local index)"),
        "reason": event.reason,
    }


def _header(message, name: str, fallback: str) -> str:
    if message is None:
        return fallback
    return _single_line(message.headers.get(name, fallback))


def _clean_snippet(snippet: str) -> str:
    normalized = _single_line(snippet)
    if len(normalized) <= 220:
        return normalized
    return f"{normalized[:217]}..."


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _gmail_url(message_id: str, *, mailbox: str = "all-mail") -> str:
    fragment = {
        "inbox": "inbox",
        "all-mail": "all",
        "trash": "trash",
    }.get(mailbox, "all")
    return f"https://mail.google.com/mail/u/0/#{fragment}/{message_id}"
