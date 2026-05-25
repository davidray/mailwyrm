import unittest

from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState
from mailwyrm.sync import SyncStats, refresh_message_from_gmail, render_sync_summary


def message(
    message_id: str = "msg-1",
    *,
    label_ids: list[str] | None = None,
    snippet: str = "Snippet",
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date="1710000000000",
        label_ids=label_ids if label_ids is not None else ["INBOX"],
        snippet=snippet,
        headers={"Subject": "Hello"},
    )


class SyncTest(unittest.TestCase):
    def test_refresh_message_from_gmail_adds_new_message(self) -> None:
        state = MailwyrmState()

        stats = refresh_message_from_gmail(state, message("msg-1"), SyncStats())

        self.assertEqual(state.messages["msg-1"].label_ids, ["INBOX"])
        self.assertEqual(
            stats,
            SyncStats(fetched=1, new=1, updated=0, unchanged=0, label_changes=0),
        )

    def test_refresh_message_from_gmail_replaces_existing_message(self) -> None:
        stale = message("msg-1", label_ids=["INBOX", "Label_1"], snippet="Old")
        refreshed = message("msg-1", label_ids=["Label_2"], snippet="Fresh")
        state = MailwyrmState(messages={"msg-1": stale})

        stats = refresh_message_from_gmail(state, refreshed, SyncStats())

        self.assertIs(state.messages["msg-1"], refreshed)
        self.assertEqual(state.messages["msg-1"].label_ids, ["Label_2"])
        self.assertEqual(state.messages["msg-1"].snippet, "Fresh")
        self.assertEqual(
            stats,
            SyncStats(fetched=1, new=0, updated=1, unchanged=0, label_changes=1),
        )

    def test_refresh_message_from_gmail_ignores_label_order_changes(self) -> None:
        stale = message("msg-1", label_ids=["INBOX", "Label_1"])
        refreshed = message("msg-1", label_ids=["Label_1", "INBOX"])
        state = MailwyrmState(messages={"msg-1": stale})

        stats = refresh_message_from_gmail(state, refreshed, SyncStats())

        self.assertEqual(
            stats,
            SyncStats(fetched=1, new=0, updated=0, unchanged=1, label_changes=0),
        )

    def test_refresh_message_from_gmail_counts_unchanged_existing_message(self) -> None:
        unchanged = message("msg-1", label_ids=[])
        state = MailwyrmState(messages={"msg-1": unchanged})

        stats = refresh_message_from_gmail(state, unchanged, SyncStats())

        self.assertEqual(state.messages["msg-1"].label_ids, [])
        self.assertEqual(
            stats,
            SyncStats(fetched=1, new=0, updated=0, unchanged=1, label_changes=0),
        )

    def test_render_sync_summary(self) -> None:
        summary = render_sync_summary(
            SyncStats(fetched=3, new=1, updated=1, unchanged=1, label_changes=1),
            "inbox",
            "user@example.com",
        )

        self.assertEqual(
            summary,
            "Synced 3 inbox message(s) for user@example.com. "
            "New: 1; updated: 1; unchanged: 1; label changes: 1.",
        )


if __name__ == "__main__":
    unittest.main()
