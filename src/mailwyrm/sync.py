from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from mailwyrm.gmail import GmailApiError
from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState


SYNC_MAILBOXES = ("inbox", "all-mail", "trash")


@dataclass(frozen=True)
class SyncStats:
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    label_changes: int = 0
    selected_message_refs: int = field(default=0, compare=False)


def sync_mailbox_from_gmail(
    client,
    state: MailwyrmState,
    *,
    limit: int | None,
    mailbox: str,
    include_body: bool = False,
    include_thread_context: bool = False,
    body_char_limit: int = 4000,
    thread_context_limit: int = 3,
) -> SyncStats:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if body_char_limit < 0:
        raise ValueError("body_char_limit must be non-negative")
    if thread_context_limit < 1:
        raise ValueError("thread_context_limit must be positive")
    if mailbox not in SYNC_MAILBOXES:
        raise ValueError("mailbox must be one of inbox, all-mail, or trash")
    if include_thread_context and not include_body:
        raise ValueError("thread context requires include_body")

    profile = client.profile()
    state.account_email = profile.get("emailAddress")
    state.history_id = profile.get("historyId")
    state.last_sync_mailbox = mailbox

    message_refs = client.list_messages(
        max_results=limit,
        label_ids=label_ids_for_mailbox(mailbox),
        include_spam_trash=include_spam_trash_for_mailbox(mailbox),
    )
    stats = SyncStats(selected_message_refs=len(message_refs))
    fetched_thread_ids: set[str] = set()
    for message_ref in message_refs:
        message_id = str(message_ref["id"])
        thread_id = message_ref.get("threadId")
        if include_body and include_thread_context and thread_id:
            if str(thread_id) in fetched_thread_ids:
                continue
            fetched_thread_ids.add(str(thread_id))
            thread = client.get_thread_full(str(thread_id))
            for thread_message in _bounded_thread_messages(
                thread.get("messages", []),
                selected_message_ids={message_id},
                limit=thread_context_limit,
            ):
                record = MessageRecord.from_gmail_message(
                    thread_message,
                    body_char_limit=body_char_limit,
                )
                stats = refresh_message_from_gmail(state, record, stats)
        elif include_body:
            message = client.get_message_full(message_id)
            record = MessageRecord.from_gmail_message(
                message,
                body_char_limit=body_char_limit,
            )
            stats = refresh_message_from_gmail(state, record, stats)
        else:
            message = client.get_message_metadata(message_id)
            record = MessageRecord.from_gmail_message(message)
            previous = state.messages.get(record.id)
            if previous is not None and previous.body_text:
                record = replace(record, body_text=previous.body_text)
            stats = refresh_message_from_gmail(state, record, stats)
    return stats


def _bounded_thread_messages(
    messages: list[Any],
    *,
    selected_message_ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    thread_messages = [message for message in messages if isinstance(message, dict)]
    if not thread_messages or limit <= 0:
        return []

    selected_indexes = [
        index
        for index, message in enumerate(thread_messages)
        if str(message.get("id", "")) in selected_message_ids
    ]
    if not selected_indexes:
        return thread_messages[-limit:]

    selected_index = selected_indexes[-1]
    start = max(0, selected_index - limit + 1)
    end = selected_index + 1
    window = thread_messages[start:end]
    if len(window) < limit:
        window.extend(thread_messages[end : end + (limit - len(window))])
    return window


def label_ids_for_mailbox(mailbox: str) -> tuple[str, ...] | None:
    if mailbox == "all-mail":
        return None
    if mailbox == "trash":
        return ("TRASH",)
    return ("INBOX",)


def include_spam_trash_for_mailbox(mailbox: str) -> bool:
    return mailbox == "trash"


@dataclass(frozen=True)
class HistoryReconcileStats:
    history_records: int = 0
    messages_fetched: int = 0
    label_changes: int = 0
    messages_deleted: int = 0
    unknown_messages: int = 0
    cursor_advanced: bool = False
    unknown_message_ids: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )
    fetched_message_ids: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )


def refresh_message_from_gmail(
    state: MailwyrmState,
    record: MessageRecord,
    stats: SyncStats,
) -> SyncStats:
    previous = state.messages.get(record.id)
    state.messages[record.id] = record

    if previous is None:
        return SyncStats(
            fetched=stats.fetched + 1,
            new=stats.new + 1,
            updated=stats.updated,
            unchanged=stats.unchanged,
            label_changes=stats.label_changes,
            selected_message_refs=stats.selected_message_refs,
        )

    changed = message_metadata_changed(previous, record)
    label_changed = set(previous.label_ids) != set(record.label_ids)
    return SyncStats(
        fetched=stats.fetched + 1,
        new=stats.new,
        updated=stats.updated + int(changed),
        unchanged=stats.unchanged + int(not changed),
        label_changes=stats.label_changes + int(label_changed),
        selected_message_refs=stats.selected_message_refs,
    )


def render_sync_summary(stats: SyncStats, mailbox: str, account_email: str | None) -> str:
    return (
        f"Synced {stats.fetched} {mailbox} message(s) for "
        f"{account_email or 'unknown account'}. "
        f"New: {stats.new}; updated: {stats.updated}; "
        f"unchanged: {stats.unchanged}; "
        f"label changes: {stats.label_changes}."
    )


def reconcile_history(
    state: MailwyrmState,
    history_response: dict[str, Any],
    *,
    client=None,
    include_body: bool = False,
    body_char_limit: int = 4000,
) -> HistoryReconcileStats:
    if body_char_limit < 0:
        raise ValueError("body_char_limit must be non-negative")

    stats = HistoryReconcileStats()
    seen_unknown_messages: set[str] = set()
    fetch_candidate_ids: set[str] = set()
    deleted_message_ids: set[str] = set()
    fetched_message_ids: set[str] = set()

    for history_record in history_response.get("history", []):
        stats = replace(stats, history_records=stats.history_records + 1)
        for added_event in history_record.get("messagesAdded", []):
            message_id = _history_message_id(added_event)
            if message_id and message_id not in state.messages:
                fetch_candidate_ids.add(message_id)

        for label_event in history_record.get("labelsAdded", []):
            message_id = _history_message_id(label_event)
            if _record_unknown_message(
                state,
                message_id,
                seen_unknown_messages,
                fetch_candidate_ids=fetch_candidate_ids,
                can_fetch=client is not None,
            ):
                continue
            label_changes = _add_labels(
                state,
                message_id,
                label_event.get("labelIds", []),
            )
            if label_changes:
                stats = replace(
                    stats,
                    label_changes=stats.label_changes + label_changes,
                )

        for label_event in history_record.get("labelsRemoved", []):
            message_id = _history_message_id(label_event)
            if _record_unknown_message(
                state,
                message_id,
                seen_unknown_messages,
                fetch_candidate_ids=fetch_candidate_ids,
                can_fetch=client is not None,
            ):
                continue
            label_changes = _remove_labels(
                state,
                message_id,
                label_event.get("labelIds", []),
            )
            if label_changes:
                stats = replace(
                    stats,
                    label_changes=stats.label_changes + label_changes,
                )

        for deleted_event in history_record.get("messagesDeleted", []):
            message_id = _history_message_id(deleted_event)
            if not message_id:
                continue
            deleted_message_ids.add(message_id)
            if message_id not in state.messages:
                seen_unknown_messages.add(message_id)
            if _remove_local_message(state, message_id):
                stats = replace(stats, messages_deleted=stats.messages_deleted + 1)

    if client is not None:
        for message_id in sorted(fetch_candidate_ids - deleted_message_ids):
            if message_id in state.messages:
                continue
            try:
                record = _fetch_history_message(
                    client,
                    message_id,
                    include_body=include_body,
                    body_char_limit=body_char_limit,
                )
            except GmailApiError as error:
                if error.status_code == 404:
                    seen_unknown_messages.add(message_id)
                    continue
                raise
            refresh_message_from_gmail(state, record, SyncStats())
            fetched_message_ids.add(message_id)
            stats = replace(stats, messages_fetched=stats.messages_fetched + 1)
            seen_unknown_messages.discard(message_id)
    else:
        seen_unknown_messages.update(fetch_candidate_ids - deleted_message_ids)

    stats = replace(
        stats,
        unknown_messages=len(seen_unknown_messages),
        unknown_message_ids=frozenset(seen_unknown_messages),
        fetched_message_ids=frozenset(fetched_message_ids),
    )
    next_history_id = history_response.get("historyId")
    if next_history_id is not None and str(next_history_id) != str(state.history_id):
        state.history_id = str(next_history_id)
        stats = replace(stats, cursor_advanced=True)
    return stats


def merge_history_stats(
    left: HistoryReconcileStats,
    right: HistoryReconcileStats,
) -> HistoryReconcileStats:
    unknown_message_ids = left.unknown_message_ids | right.unknown_message_ids
    fetched_message_ids = left.fetched_message_ids | right.fetched_message_ids
    return HistoryReconcileStats(
        history_records=left.history_records + right.history_records,
        messages_fetched=left.messages_fetched + right.messages_fetched,
        label_changes=left.label_changes + right.label_changes,
        messages_deleted=left.messages_deleted + right.messages_deleted,
        unknown_messages=len(unknown_message_ids),
        cursor_advanced=left.cursor_advanced or right.cursor_advanced,
        unknown_message_ids=unknown_message_ids,
        fetched_message_ids=fetched_message_ids,
    )


def render_history_reconcile_summary(
    stats: HistoryReconcileStats,
    account_email: str | None,
) -> str:
    cursor = "advanced" if stats.cursor_advanced else "unchanged"
    return (
        f"Reconciled {stats.history_records} Gmail history record(s) for "
        f"{account_email or 'unknown account'}. "
        f"Fetched messages: {stats.messages_fetched}; "
        f"Label changes: {stats.label_changes}; "
        f"deleted messages: {stats.messages_deleted}; "
        f"unknown messages: {stats.unknown_messages}; "
        f"cursor: {cursor}."
    )


def _history_message_id(event: dict[str, Any]) -> str:
    message = event.get("message") or {}
    message_id = message.get("id")
    return "" if message_id is None else str(message_id)


def _record_unknown_message(
    state: MailwyrmState,
    message_id: str,
    seen_unknown_messages: set[str],
    *,
    fetch_candidate_ids: set[str] | None = None,
    can_fetch: bool = False,
) -> bool:
    if not message_id or message_id not in state.messages:
        if message_id:
            if can_fetch and fetch_candidate_ids is not None:
                fetch_candidate_ids.add(message_id)
            else:
                seen_unknown_messages.add(message_id)
        return True
    return False


def _fetch_history_message(
    client,
    message_id: str,
    *,
    include_body: bool,
    body_char_limit: int,
) -> MessageRecord:
    if include_body:
        message = client.get_message_full(message_id)
        return MessageRecord.from_gmail_message(
            message,
            body_char_limit=body_char_limit,
        )
    message = client.get_message_metadata(message_id)
    return MessageRecord.from_gmail_message(message)


def _add_labels(
    state: MailwyrmState,
    message_id: str,
    label_ids: list[str],
) -> int:
    message = state.messages[message_id]
    existing = set(message.label_ids)
    updated = existing | {str(label_id) for label_id in label_ids}
    if updated == existing:
        return 0
    state.messages[message_id] = replace(message, label_ids=sorted(updated))
    return len(updated - existing)


def _remove_labels(
    state: MailwyrmState,
    message_id: str,
    label_ids: list[str],
) -> int:
    message = state.messages[message_id]
    existing = set(message.label_ids)
    updated = existing - {str(label_id) for label_id in label_ids}
    if updated == existing:
        return 0
    state.messages[message_id] = replace(message, label_ids=sorted(updated))
    return len(existing - updated)


def _remove_local_message(state: MailwyrmState, message_id: str) -> bool:
    removed = False
    for records in (state.messages, state.classifications, state.corrections):
        if records.pop(message_id, None) is not None:
            removed = True
    return removed


def message_metadata_changed(previous: MessageRecord, record: MessageRecord) -> bool:
    return (
        previous.id != record.id
        or previous.thread_id != record.thread_id
        or previous.history_id != record.history_id
        or previous.internal_date != record.internal_date
        or set(previous.label_ids) != set(record.label_ids)
        or previous.snippet != record.snippet
        or previous.headers != record.headers
        or previous.body_text != record.body_text
    )
