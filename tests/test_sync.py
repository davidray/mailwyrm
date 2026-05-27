import unittest

from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState
from mailwyrm.sync import (
    HistoryReconcileStats,
    merge_history_stats,
    refresh_message_from_gmail,
    reconcile_history,
    render_history_reconcile_summary,
    render_sync_summary,
    sync_mailbox_from_gmail,
    SyncStats,
)


def message(
    message_id: str = "msg-1",
    *,
    label_ids: list[str] | None = None,
    snippet: str = "Snippet",
    body_text: str = "",
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id="thread-1",
        history_id="10",
        internal_date="1710000000000",
        label_ids=label_ids if label_ids is not None else ["INBOX"],
        snippet=snippet,
        headers={"Subject": "Hello"},
        body_text=body_text,
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

    def test_refresh_message_from_gmail_counts_body_text_updates(self) -> None:
        stale = message("msg-1", body_text="Old body")
        refreshed = message("msg-1", body_text="Fresh body")
        state = MailwyrmState(messages={"msg-1": stale})

        stats = refresh_message_from_gmail(state, refreshed, SyncStats())

        self.assertEqual(state.messages["msg-1"].body_text, "Fresh body")
        self.assertEqual(
            stats,
            SyncStats(fetched=1, new=0, updated=1, unchanged=0, label_changes=0),
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

    def test_sync_mailbox_from_gmail_fetches_bodies_for_app_workflow(self) -> None:
        state = MailwyrmState()
        client = FakeSyncClient()

        stats = sync_mailbox_from_gmail(
            client,
            state,
            limit=10,
            mailbox="inbox",
            include_body=True,
            body_char_limit=9,
        )

        self.assertEqual(stats, SyncStats(fetched=1, new=1))
        self.assertEqual(state.account_email, "user@example.com")
        self.assertEqual(state.history_id, "42")
        self.assertEqual(state.last_sync_mailbox, "inbox")
        self.assertEqual(client.list_kwargs["label_ids"], ("INBOX",))
        self.assertEqual(client.full_message_ids, ["msg-1"])
        self.assertEqual(client.metadata_message_ids, [])
        self.assertEqual(state.messages["msg-1"].body_text, "Body text")

    def test_sync_mailbox_from_gmail_preserves_body_on_metadata_refresh(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", body_text="Previously synced body."),
            }
        )
        client = FakeSyncClient()

        stats = sync_mailbox_from_gmail(
            client,
            state,
            limit=10,
            mailbox="all-mail",
        )

        self.assertEqual(stats, SyncStats(fetched=1, unchanged=1))
        self.assertIsNone(client.list_kwargs["label_ids"])
        self.assertEqual(client.metadata_message_ids, ["msg-1"])
        self.assertEqual(client.full_message_ids, [])
        self.assertEqual(state.messages["msg-1"].body_text, "Previously synced body.")

    def test_reconcile_history_applies_label_adds_and_removes(self) -> None:
        state = MailwyrmState(
            history_id="100",
            messages={
                "msg-1": message("msg-1", label_ids=["INBOX", "UNREAD"]),
            },
        )

        stats = reconcile_history(
            state,
            {
                "historyId": "105",
                "history": [
                    {
                        "labelsAdded": [
                            {"message": {"id": "msg-1"}, "labelIds": ["TRASH"]}
                        ],
                        "labelsRemoved": [
                            {"message": {"id": "msg-1"}, "labelIds": ["INBOX"]}
                        ],
                    }
                ],
            },
        )

        self.assertEqual(state.messages["msg-1"].label_ids, ["TRASH", "UNREAD"])
        self.assertEqual(
            stats,
            HistoryReconcileStats(
                history_records=1,
                label_changes=2,
                messages_deleted=0,
                unknown_messages=0,
                cursor_advanced=True,
            ),
        )
        self.assertEqual(state.history_id, "105")

    def test_reconcile_history_counts_each_label_changed(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1", label_ids=["INBOX", "UNREAD"]),
            },
        )

        stats = reconcile_history(
            state,
            {
                "history": [
                    {
                        "labelsAdded": [
                            {
                                "message": {"id": "msg-1"},
                                "labelIds": ["Label_1", "Label_2"],
                            }
                        ],
                        "labelsRemoved": [
                            {
                                "message": {"id": "msg-1"},
                                "labelIds": ["INBOX", "UNREAD", "MISSING"],
                            }
                        ],
                    }
                ],
            },
        )

        self.assertEqual(state.messages["msg-1"].label_ids, ["Label_1", "Label_2"])
        self.assertEqual(stats.label_changes, 4)

    def test_reconcile_history_removes_deleted_local_messages(self) -> None:
        state = MailwyrmState(
            messages={
                "msg-1": message("msg-1"),
                "msg-2": message("msg-2"),
            },
        )
        state.classifications["msg-1"] = object()
        state.corrections["msg-1"] = object()

        stats = reconcile_history(
            state,
            {
                "historyId": "105",
                "history": [
                    {
                        "messagesDeleted": [
                            {"message": {"id": "msg-1"}},
                        ],
                    }
                ],
            },
        )

        self.assertNotIn("msg-1", state.messages)
        self.assertNotIn("msg-1", state.classifications)
        self.assertNotIn("msg-1", state.corrections)
        self.assertIn("msg-2", state.messages)
        self.assertEqual(stats.messages_deleted, 1)

    def test_reconcile_history_removes_deleted_orphaned_local_records(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})
        state.classifications["missing"] = object()
        state.corrections["missing"] = object()

        stats = reconcile_history(
            state,
            {
                "history": [
                    {
                        "messagesDeleted": [
                            {"message": {"id": "missing"}},
                        ],
                    }
                ],
            },
        )

        self.assertNotIn("missing", state.classifications)
        self.assertNotIn("missing", state.corrections)
        self.assertEqual(stats.messages_deleted, 1)
        self.assertEqual(stats.unknown_messages, 1)

    def test_reconcile_history_counts_unknown_messages_once_per_response(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        stats = reconcile_history(
            state,
            {
                "history": [
                    {
                        "labelsAdded": [
                            {"message": {"id": "missing"}, "labelIds": ["INBOX"]},
                        ],
                        "labelsRemoved": [
                            {"message": {"id": "missing"}, "labelIds": ["UNREAD"]},
                        ],
                    }
                ],
            },
        )

        self.assertEqual(stats.unknown_messages, 1)

    def test_merge_history_stats_deduplicates_unknown_messages(self) -> None:
        merged = merge_history_stats(
            HistoryReconcileStats(
                history_records=1,
                unknown_messages=2,
                unknown_message_ids=frozenset({"missing-1", "missing-2"}),
            ),
            HistoryReconcileStats(
                history_records=1,
                unknown_messages=2,
                unknown_message_ids=frozenset({"missing-2", "missing-3"}),
            ),
        )

        self.assertEqual(merged.history_records, 2)
        self.assertEqual(merged.unknown_messages, 3)

    def test_render_history_reconcile_summary(self) -> None:
        summary = render_history_reconcile_summary(
            HistoryReconcileStats(
                history_records=2,
                label_changes=3,
                messages_deleted=1,
                unknown_messages=4,
                cursor_advanced=True,
            ),
            "user@example.com",
        )

        self.assertEqual(
            summary,
            "Reconciled 2 Gmail history record(s) for user@example.com. "
            "Label changes: 3; deleted messages: 1; unknown messages: 4; "
            "cursor: advanced.",
        )


class FakeSyncClient:
    def __init__(self) -> None:
        self.metadata_message_ids: list[str] = []
        self.full_message_ids: list[str] = []
        self.list_kwargs = {}

    def profile(self):
        return {"emailAddress": "user@example.com", "historyId": "42"}

    def list_messages(self, **kwargs):
        self.list_kwargs = kwargs
        return [{"id": "msg-1"}]

    def get_message_metadata(self, message_id):
        self.metadata_message_ids.append(message_id)
        return self._message()

    def get_message_full(self, message_id):
        self.full_message_ids.append(message_id)
        return {
            **self._message(),
            "payload": {
                "headers": [{"name": "Subject", "value": "Hello"}],
                "mimeType": "text/plain",
                "body": {"data": "Qm9keSB0ZXh0IGZvciBjbGFzc2lmaWNhdGlvbg"},
            },
        }

    def _message(self):
        return {
            "id": "msg-1",
            "threadId": "thread-1",
            "historyId": "10",
            "internalDate": "1710000000000",
            "labelIds": ["INBOX"],
            "snippet": "Snippet",
            "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
        }


if __name__ == "__main__":
    unittest.main()
