from __future__ import annotations

import re
from email.utils import parseaddr
from shlex import quote
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mailwyrm.actions import (
    ACTION_ARCHIVE_AFTER_DIGEST,
    ACTION_KEEP,
    ACTION_PROTECT,
    ACTION_REVIEW,
    ACTION_TRASH_AFTER_DIGEST,
    GMAIL_INBOX_LABEL,
    GMAIL_TRASH_LABEL,
    build_action_plans,
    build_trash_preview,
    message_matches_mailbox,
    plan_action,
)
from mailwyrm.corrections import effective_classification
from mailwyrm.digest import build_digest_items
from mailwyrm.digest import build_digest_bundles
from mailwyrm.labels import build_label_plans
from mailwyrm.models import MACHINE_TYPES, normalize_email_text
from mailwyrm.store import MailwyrmState


SUPPORTED_MAILBOXES = ("inbox", "all-mail", "trash")


def build_daily_cockpit_payload(
    state: MailwyrmState,
    *,
    title_date: str | None = None,
    limit: int | None = 25,
    mailbox: str = "inbox",
    audit_limit: int = 10,
    client_secret: Path | None = None,
) -> dict[str, Any]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if audit_limit < 0:
        raise ValueError("audit_limit must be non-negative")
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError("mailbox must be one of inbox, all-mail, or trash")

    title_date = title_date or datetime.now(UTC).date().isoformat()
    all_action_plans = build_action_plans(state, mailbox=mailbox)
    action_plans = all_action_plans if limit is None else all_action_plans[:limit]
    trash_preview = build_trash_preview(state, limit=limit, mailbox=mailbox)
    all_digest_items = build_digest_items(state, mailbox=mailbox)
    digest_items = all_digest_items if limit is None else all_digest_items[:limit]
    digest_bundles = build_digest_bundles(state, limit=limit, mailbox=mailbox)
    attention_lanes = _attention_lanes(state, mailbox=mailbox, limit=limit)
    audit_events = sorted(
        state.label_audit_events,
        key=lambda event: event.created_at,
        reverse=True,
    )
    visible_audit_events = audit_events[:audit_limit]

    return {
        "title": "Bookwyrm Mail Correspondence",
        "date": title_date,
        "read_only": True,
        "account": {
            "email": state.account_email or "unknown",
            "avatar_url": None,
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
        "cleanup": _cleanup_payload(
            action_plans=action_plans,
            trash_preview=trash_preview,
            mailbox=mailbox,
            limit=limit,
            policy=state.automation_policy,
            client_secret=client_secret,
            digested_message_ids={
                event.message_id for event in state.digest_audit_events
            },
        ),
        "lanes": attention_lanes,
        "digest": {
            "total_items": len(all_digest_items),
            "showing_items": len(digest_items),
            "items": [_digest_item_payload(item) for item in digest_items],
            "bundles": [
                _digest_bundle_payload(bundle, mailbox=mailbox, state=state)
                for bundle in digest_bundles
            ],
        },
        "mailbox_actions": {
            "mailbox": mailbox,
            "counts": _action_counts(action_plans),
            "total_plans": len(all_action_plans),
            "showing_plans": len(action_plans),
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
            client_secret=client_secret,
        ),
        "commands": _useful_commands(client_secret=client_secret),
        "configuration": {
            "client_secret_configured": client_secret is not None,
        },
    }


def _useful_commands(*, client_secret: Path | None) -> list[str]:
    client_secret_arg = _client_secret_arg(client_secret)
    return [
        "uv run mailwyrm sync --mailbox inbox --limit 25"
        f"{client_secret_arg}",
        "uv run mailwyrm classify",
        "uv run mailwyrm daily apply --limit 25"
        f"{client_secret_arg}",
        "uv run mailwyrm actions apply-trash --limit 10"
        f"{client_secret_arg}",
    ]


def _cleanup_payload(
    *,
    action_plans,
    trash_preview,
    mailbox: str,
    limit: int | None,
    policy,
    client_secret: Path | None,
    digested_message_ids: set[str],
) -> dict[str, Any]:
    action_counts = _action_counts(action_plans)
    archive_candidates = [
        plan
        for plan in action_plans
        if plan.action == ACTION_ARCHIVE_AFTER_DIGEST
        and GMAIL_INBOX_LABEL in plan.message.label_ids
    ]
    archive_ready = [
        plan
        for plan in archive_candidates
        if plan.message.id in digested_message_ids
    ]
    archive_waiting_for_digest = [
        plan for plan in archive_candidates if plan.message.id not in digested_message_ids
    ]
    trash_candidates = [
        plan
        for plan in action_plans
        if plan.action == ACTION_TRASH_AFTER_DIGEST
        and GMAIL_TRASH_LABEL not in plan.message.label_ids
    ]
    trash_ready = [
        plan for plan in trash_candidates if plan.message.id in digested_message_ids
    ]
    trash_waiting_for_digest = len(trash_candidates) - len(trash_ready)
    review_or_protected = action_counts[ACTION_REVIEW] + action_counts[ACTION_PROTECT]
    kept_human = action_counts[ACTION_KEEP]
    limit_arg = "" if limit is None else f" --limit {limit}"
    mailbox_arg = f" --mailbox {mailbox}"
    client_secret_arg = _client_secret_arg(client_secret)

    return {
        "mailbox": mailbox,
        "clearable_now": len(archive_ready) + len(trash_ready),
        "archive": {
            "ready": len(archive_ready),
            "candidates": len(archive_candidates),
            "waiting_for_digest": len(archive_waiting_for_digest),
            "preview_command": (
                "uv run mailwyrm actions preview"
                f"{mailbox_arg}{limit_arg}"
            ),
            "apply_command": (
                "uv run mailwyrm actions apply-archive"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
            ),
        },
        "trash": {
            "ready": len(trash_ready),
            "candidates": len(trash_candidates),
            "waiting_for_digest": trash_waiting_for_digest,
            "policy_enabled": policy.trash_after_digest_enabled,
            "preview_command": (
                "uv run mailwyrm actions preview-trash"
                f"{mailbox_arg}{limit_arg}"
            ),
            "apply_command": (
                "uv run mailwyrm actions apply-trash"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
            ),
        },
        "protected_or_review": review_or_protected,
        "kept_human": kept_human,
    }


def build_message_detail_payload(
    state: MailwyrmState,
    *,
    message_id: str,
    mailbox: str = "inbox",
) -> dict[str, Any]:
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError("mailbox must be one of inbox, all-mail, or trash")
    message = state.messages.get(message_id)
    if message is None:
        raise KeyError(message_id)

    classification = state.classifications.get(message.id)
    correction = state.corrections.get(message.id)
    effective = (
        effective_classification(classification, correction)
        if classification is not None
        else None
    )
    plan = plan_action(message, effective) if effective is not None else None
    audit_events = sorted(
        (
            event
            for event in state.label_audit_events
            if event.message_id == message.id
        ),
        key=lambda event: event.created_at,
        reverse=True,
    )
    conversation = _conversation_payload(
        state,
        thread_id=message.thread_id,
        selected_message_id=message.id,
        mailbox=mailbox,
    )

    return {
        "title": _header(message, "Subject", "(no subject)"),
        "read_only": True,
        "reply_available": False,
        "reply_status": "Draft replies are not enabled yet.",
        "message": {
            "message_id": message.id,
            "thread_id": message.thread_id,
            "gmail_url": _gmail_url(message.id, mailbox=mailbox),
            "subject": _header(message, "Subject", "(no subject)"),
            "sender": _header(message, "From", "(unknown sender)"),
            "to": _header(message, "To", ""),
            "date": _header(message, "Date", ""),
            "message_id_header": _header(message, "Message-ID", ""),
            "label_ids": list(message.label_ids),
            "snippet": _clean_snippet(message.snippet),
            "body_text": message.body_text,
            "has_body_text": bool(message.body_text),
        },
        "conversation": conversation,
        "classification": (
            _classification_payload(effective)
            if effective is not None
            else None
        ),
        "correction": (
            {
                "category": correction.category,
                "machine_type": correction.machine_type,
                "reason": correction.reason,
                "suggested_actions": list(correction.suggested_actions or []),
                "importance": correction.importance,
                "automation_safety": correction.automation_safety,
            }
            if correction is not None
            else None
        ),
        "review_resolution": _review_resolution_payload(
            classification=classification,
            effective=effective,
        ),
        "suggested_action": (
            {
                "action": plan.action,
                "reason": plan.reason,
                "mutates_gmail": _action_mutates_gmail(plan.action),
            }
            if plan is not None
            else None
        ),
        "audit": [_audit_event_payload(state, event) for event in audit_events],
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


def _conversation_payload(
    state: MailwyrmState,
    *,
    thread_id: str,
    selected_message_id: str,
    mailbox: str,
) -> list[dict[str, Any]]:
    messages = [
        message
        for message in state.messages.values()
        if message.thread_id == thread_id
    ]
    messages.sort(key=lambda message: message.internal_date or "")
    return [
        {
            "message_id": message.id,
            "selected": message.id == selected_message_id,
            "gmail_url": _gmail_url(message.id, mailbox=mailbox),
            "subject": _header(message, "Subject", "(no subject)"),
            "sender": _header(message, "From", "(unknown sender)"),
            "to": _header(message, "To", ""),
            "date": _header(message, "Date", ""),
            "snippet": _clean_snippet(message.snippet),
            "body_text": message.body_text,
            "has_body_text": bool(message.body_text),
        }
        for message in messages
    ]


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


def _action_mutates_gmail(action: str) -> bool:
    return action in {ACTION_ARCHIVE_AFTER_DIGEST, ACTION_TRASH_AFTER_DIGEST}


def _workflow_controls(
    *,
    state: MailwyrmState,
    mailbox: str,
    limit: int | None,
    action_plans,
    trash_preview,
    policy,
    client_secret: Path | None,
) -> list[dict[str, Any]]:
    limit_arg = "" if limit is None else f" --limit {limit}"
    mailbox_arg = f" --mailbox {mailbox}"
    action_counts = _action_counts(action_plans)
    archive_count = action_counts[ACTION_ARCHIVE_AFTER_DIGEST]
    trash_count = len(trash_preview.plans)
    label_count = len(build_label_plans(state, limit=limit, mailbox=mailbox))
    classify_count = _unclassified_message_count(state, mailbox=mailbox, limit=limit)
    client_secret_arg = _client_secret_arg(client_secret)

    return [
        {
            "id": "sync",
            "title": "Full sync from Gmail",
            "phase": "Read",
            "status": "Repair",
            "count": None,
            "mutates_gmail": False,
            "description": "Rebuild the full local index from Gmail for this mailbox scope.",
            "app_action": "sync",
            "action_label": "Run full sync",
            "sync_all": True,
            "primary_command": (
                "uv run mailwyrm sync"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
            ),
        },
        {
            "id": "classify",
            "title": "Classify local mail",
            "phase": "AI",
            "status": "Local only",
            "count": classify_count,
            "mutates_gmail": False,
            "description": "Classify all indexed messages in this mailbox scope.",
            "app_action": "classify",
            "action_label": "Classify",
            "process_all": True,
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
            "app_action": "labels",
            "action_label": "Apply labels",
            "preview_command": (
                "uv run mailwyrm labels preview"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm labels apply"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
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
            "app_action": "archive",
            "action_label": "Archive",
            "preview_command": (
                "uv run mailwyrm actions preview"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm actions apply-archive"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
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
            "app_action": "trash",
            "action_label": "Move to Trash",
            "preview_command": (
                "uv run mailwyrm actions preview-trash"
                f"{mailbox_arg}{limit_arg}"
            ),
            "primary_command": (
                "uv run mailwyrm actions apply-trash"
                f"{mailbox_arg}{limit_arg}"
                f"{client_secret_arg}"
            ),
        },
    ]


def _client_secret_arg(client_secret: Path | None) -> str:
    if client_secret is None:
        return " --client-secret /path/to/client_secret.json"
    return f" --client-secret {quote(str(client_secret.expanduser()))}"


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
            "people": [],
        },
        "needs_review": {
            "total_items": 0,
            "showing_items": 0,
            "review_types": {},
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
        if lane_name == "needs_review":
            review_type = _review_type_payload(classification)
            if review_type is not None:
                lane["review_types"][review_type] = (
                    lane["review_types"].get(review_type, 0) + 1
                )
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
    lanes["human"]["people"] = _people_groups(lanes["human"]["items"])
    return lanes


def _people_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        sender_name, sender_email = _person_from_sender(item["sender"])
        key = sender_email.lower() if sender_email else sender_name.lower()
        group = groups.setdefault(
            key,
            {
                "name": sender_name,
                "email": sender_email,
                "sender": item["sender"],
                "count": 0,
                "items": [],
                "order": len(groups),
            },
        )
        group["count"] += 1
        group["items"].append(item)
    people = sorted(groups.values(), key=lambda group: group["order"])
    for group in people:
        del group["order"]
        group["items"] = _conversation_groups(group["items"])
        group["conversation_count"] = len(group["items"])
    return people


def _conversation_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        group = groups.setdefault(
            item["thread_id"],
            {
                **item,
                "message_count": 0,
                "message_ids": [],
                "order": len(groups),
            },
        )
        group["message_count"] += 1
        group["message_ids"].append(item["message_id"])
    conversations = sorted(groups.values(), key=lambda group: group["order"])
    for conversation in conversations:
        del conversation["order"]
    return conversations


def _person_from_sender(sender: str) -> tuple[str, str]:
    name, email = parseaddr(sender)
    if not name and email:
        name = email
    if not name:
        name = sender or "(unknown sender)"
    return _single_line(name), _single_line(email)


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
        "review_type": _review_type_payload(classification),
        "importance": classification.importance,
        "automation_safety": classification.automation_safety,
        "confidence": classification.confidence,
        "reason": classification.reason,
    }


def _digest_bundle_payload(
    bundle,
    *,
    mailbox: str,
    state: MailwyrmState,
) -> dict[str, Any]:
    followup_count = sum(
        1 for item in bundle.items if item.message.id in state.followups
    )
    read_later_count = sum(
        1 for item in bundle.items if item.message.id in state.read_later
    )
    return {
        "machine_type": bundle.machine_type,
        "title": bundle.title,
        "count": bundle.count,
        "followup_count": followup_count,
        "read_later_count": read_later_count,
        "mailbox": mailbox,
        "action": "trash",
        "action_label": f"Got it: trash {bundle.title.lower()}",
        "sender_groups": _digest_sender_groups(
            bundle.items,
            state=state,
            mailbox=mailbox,
            group_by_sender=_group_digest_category_by_sender(bundle.machine_type),
        ),
    }


def _group_digest_category_by_sender(machine_type: str) -> bool:
    return machine_type != "news"


def _digest_sender_groups(
    items,
    *,
    state: MailwyrmState,
    mailbox: str,
    group_by_sender: bool,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        sender = _header(item.message, "From", "(unknown sender)")
        sender_name, sender_email = _person_from_sender(sender)
        key = (
            sender_email.lower()
            if group_by_sender and sender_email
            else sender_name.lower()
        )
        if not group_by_sender:
            key = item.message.id
        group = groups.setdefault(
            key,
            {
                "sender": sender,
                "sender_name": sender_name,
                "sender_email": sender_email,
                "count": 0,
                "message_ids": [],
                "followup_count": 0,
                "read_later_count": 0,
                "subjects": [],
                "messages": [],
                "summaries": [],
                "gmail_url": _gmail_url(item.message.id, mailbox=mailbox),
                "order": len(groups),
            },
        )
        group["count"] += 1
        group["message_ids"].append(item.message.id)
        group["messages"].append(
            {
                    "message_id": item.message.id,
                    "subject": _header(item.message, "Subject", "(no subject)"),
                    "gmail_url": _gmail_url(item.message.id, mailbox=mailbox),
                }
        )
        if item.message.id in state.followups:
            group["followup_count"] += 1
        if item.message.id in state.read_later:
            group["read_later_count"] += 1
        group["subjects"].append(_header(item.message, "Subject", "(no subject)"))
        summary = _clean_snippet(item.message.body_text or item.message.snippet)
        group["summaries"].append(summary)

    sender_groups = sorted(groups.values(), key=lambda group: group["order"])
    for group in sender_groups:
        del group["order"]
        group["subject"] = group["subjects"][0] if group["count"] == 1 else ""
        group["summary"] = _digest_sender_summary(group)
        del group["summaries"]
    return sender_groups


def _digest_sender_summary(group: dict[str, Any]) -> str:
    subjects = group["subjects"]
    summaries = group["summaries"]
    if group["count"] == 1:
        return summaries[0] if summaries and summaries[0] else subjects[0]

    parts = []
    for index, subject in enumerate(subjects[:3]):
        summary = summaries[index] if index < len(summaries) else ""
        if summary and summary != subject:
            parts.append(f"{subject} - {_summary_excerpt(summary, 120)}")
        else:
            parts.append(subject)
    hidden = group["count"] - 3
    suffix = f"; +{hidden} more" if hidden > 0 else ""
    return f"{group['count']} messages: {'; '.join(parts)}{suffix}"


def _summary_excerpt(summary: str, max_length: int) -> str:
    if len(summary) <= max_length:
        return summary
    return f"{summary[: max_length - 3]}..."


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
        "review_type": _review_type_payload(classification),
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
        "review_type": _review_type_payload(plan.classification),
        "confidence": plan.classification.confidence,
        "action": plan.action,
        "reason": plan.reason,
    }


def _classification_payload(classification) -> dict[str, Any]:
    return {
        "category": classification.category,
        "machine_type": classification.machine_type,
        "review_type": _review_type_payload(classification),
        "importance": classification.importance,
        "automation_safety": classification.automation_safety,
        "confidence": classification.confidence,
        "reason": classification.reason,
        "suggested_actions": list(classification.suggested_actions),
        "classifier_version": classification.classifier_version,
    }


def _review_resolution_payload(*, classification, effective) -> dict[str, Any]:
    is_review = (
        classification is not None
        and classification.category == "needs_review"
        and (effective is None or effective.category == "needs_review")
    )
    return {
        "available": bool(is_review),
        "resolutions": [
            {
                "id": "human",
                "label": "Real People",
                "description": "Move to Real People.",
                "requires_machine_type": False,
            },
        ],
        "machine_types": list(MACHINE_TYPES),
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


def _review_type_payload(classification) -> str | None:
    if classification.category != "needs_review":
        return None
    return classification.review_type or "unknown"


def _header(message, name: str, fallback: str) -> str:
    if message is None:
        return fallback
    return _single_line(message.headers.get(name, fallback))


def _clean_snippet(snippet: str) -> str:
    normalized = _single_line(normalize_email_text(snippet))
    normalized = re.sub(r"(^|\s)#{1,6}\s+", r"\1", normalized)
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
