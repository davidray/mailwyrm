from __future__ import annotations

from dataclasses import dataclass

from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState


@dataclass(frozen=True)
class SyncStats:
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    label_changes: int = 0


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
        )

    changed = message_metadata_changed(previous, record)
    label_changed = set(previous.label_ids) != set(record.label_ids)
    return SyncStats(
        fetched=stats.fetched + 1,
        new=stats.new,
        updated=stats.updated + int(changed),
        unchanged=stats.unchanged + int(not changed),
        label_changes=stats.label_changes + int(label_changed),
    )


def render_sync_summary(stats: SyncStats, mailbox: str, account_email: str | None) -> str:
    return (
        f"Synced {stats.fetched} {mailbox} message(s) for "
        f"{account_email or 'unknown account'}. "
        f"New: {stats.new}; updated: {stats.updated}; "
        f"unchanged: {stats.unchanged}; "
        f"label changes: {stats.label_changes}."
    )


def message_metadata_changed(previous: MessageRecord, record: MessageRecord) -> bool:
    return (
        previous.id != record.id
        or previous.thread_id != record.thread_id
        or previous.history_id != record.history_id
        or previous.internal_date != record.internal_date
        or set(previous.label_ids) != set(record.label_ids)
        or previous.snippet != record.snippet
        or previous.headers != record.headers
    )
