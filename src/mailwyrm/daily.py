from __future__ import annotations

from mailwyrm.actions import (
    ACTION_ARCHIVE_AFTER_DIGEST,
    ACTION_PROTECT,
    ACTION_REVIEW,
    ACTION_RESTORE_ARCHIVE,
    ACTION_RESTORE_TRASH,
    ACTION_TRASH_AFTER_DIGEST,
    GMAIL_INBOX_LABEL,
    build_action_plans,
    render_action_preview,
)
from mailwyrm.digest import render_digest
from mailwyrm.labels import DIGESTED_LABEL
from mailwyrm.labels import build_digested_label_plans, render_digested_label_preview
from mailwyrm.store import MailwyrmState


def render_daily_preview(
    state: MailwyrmState,
    *,
    title_date: str,
    limit: int | None = None,
    mailbox: str = "inbox",
    mutates_gmail: bool = False,
) -> str:
    digested_label_plans = build_digested_label_plans(state, limit=limit)
    action_plans = build_action_plans(state, limit=limit, mailbox=mailbox)
    mutation_notice = (
        "Gmail labels and archive state may be changed after this report. Trash is not applied."
        if mutates_gmail
        else "This is a preview. No Gmail labels, archive state, or local digest audit state will be changed."
    )

    sections = [
        f"# Mailwyrm Daily Preview - {title_date}",
        "",
        mutation_notice,
        "",
        "## Machine Digest",
        "",
        render_digest(state, title_date=title_date),
        "",
        "## Gmail Digested Labels",
        "",
        "Candidates come from messages that already have local digest audit events.",
        "",
        render_digested_label_preview(digested_label_plans),
        "",
        "## Mailbox Actions",
        "",
        f"Mailbox scope: {mailbox}",
        "Archive apply remains gated to messages that have appeared in a digest.",
        "",
        render_action_preview(action_plans, mutates_gmail=mutates_gmail),
        "",
    ]
    return "\n".join(sections)


def render_daily_status(state: MailwyrmState, *, mailbox: str = "inbox") -> str:
    action_plans = build_action_plans(state, mailbox=mailbox)
    action_counts = _counts(plan.action for plan in action_plans)
    label_action_counts = _counts(event.action for event in state.label_audit_events)
    digest_runs = _counts(event.digest_title_date for event in state.digest_audit_events)
    digested_message_ids = {
        event.message_id for event in state.digest_audit_events
    }
    skipped_archive_candidates = [
        plan
        for plan in action_plans
        if plan.action == ACTION_ARCHIVE_AFTER_DIGEST
        and GMAIL_INBOX_LABEL in plan.message.label_ids
        and plan.message.id not in digested_message_ids
    ]

    last_digest_date = _latest_or_unknown(
        event.digest_title_date for event in state.digest_audit_events
    )
    last_label_action_at = _latest_or_unknown(
        event.created_at for event in state.label_audit_events
    )
    digested_label_events = [
        event
        for event in state.label_audit_events
        if event.action == "add_digested_label" or DIGESTED_LABEL in event.label_names
    ]
    archived_events = [
        event
        for event in state.label_audit_events
        if event.action == ACTION_ARCHIVE_AFTER_DIGEST
    ]
    restored_events = [
        event
        for event in state.label_audit_events
        if event.action == ACTION_RESTORE_ARCHIVE
    ]
    trashed_events = [
        event
        for event in state.label_audit_events
        if event.action == ACTION_TRASH_AFTER_DIGEST
    ]
    restored_trash_events = [
        event
        for event in state.label_audit_events
        if event.action == ACTION_RESTORE_TRASH
    ]

    lines = [
        "# Mailwyrm Daily Status",
        "",
        f"Account: {state.account_email or 'unknown'}",
        f"Last sync mailbox: {state.last_sync_mailbox or 'unknown'}",
        f"Indexed messages: {len(state.messages)}",
        f"Classified messages: {len(state.classifications)}",
        "",
        "## Digest Audit",
        "",
        f"Digest audit events: {len(state.digest_audit_events)}",
        f"Unique digested messages: {len({event.message_id for event in state.digest_audit_events})}",
        f"Last digest date: {last_digest_date}",
        "",
        "## Gmail Mutation Audit",
        "",
        f"Digested label events: {len(digested_label_events)}",
        f"Archive events: {len(archived_events)}",
        f"Restore archive events: {len(restored_events)}",
        f"Trash events: {len(trashed_events)}",
        f"Restore trash events: {len(restored_trash_events)}",
        f"Last Gmail mutation audit: {last_label_action_at}",
        "",
        "## Current Mailbox Plan",
        "",
        f"Mailbox scope: {mailbox}",
        f"Protect: {action_counts.get(ACTION_PROTECT, 0)}",
        f"Review: {action_counts.get(ACTION_REVIEW, 0)}",
        f"Archive after digest: {action_counts.get(ACTION_ARCHIVE_AFTER_DIGEST, 0)}",
        f"Archive candidates not yet digested: {len(skipped_archive_candidates)}",
        f"Trash after digest candidates: {action_counts.get(ACTION_TRASH_AFTER_DIGEST, 0)}",
        "",
        "## Recent Digest Runs",
        "",
    ]
    if digest_runs:
        for digest_date in sorted(digest_runs, reverse=True)[:5]:
            lines.append(f"- {digest_date}: {digest_runs[digest_date]}")
    else:
        lines.append("No digest audit events yet.")

    lines.extend(["", "## Gmail Audit Event Types", ""])
    if label_action_counts:
        for action in sorted(label_action_counts):
            lines.append(f"- {action}: {label_action_counts[action]}")
    else:
        lines.append("No Gmail mutation audit events yet.")

    return "\n".join(lines)


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _latest_or_unknown(values) -> str:
    known_values = [value for value in values if value]
    if not known_values:
        return "unknown"
    return max(known_values)
