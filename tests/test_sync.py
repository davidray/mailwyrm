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

    def test_sync_mailbox_from_gmail_fetches_bounded_thread_context(self) -> None:
        state = MailwyrmState()
        client = FakeSyncClient()
        client.message_refs = [{"id": "msg-1", "threadId": "thread-1"}]

        stats = sync_mailbox_from_gmail(
            client,
            state,
            limit=10,
            mailbox="inbox",
            include_body=True,
            include_thread_context=True,
            body_char_limit=12,
        )

        self.assertEqual(stats, SyncStats(fetched=2, new=2))
        self.assertEqual(stats.selected_message_refs, 1)
        self.assertEqual(client.thread_ids, ["thread-1"])
        self.assertEqual(client.full_message_ids, [])
        self.assertEqual(set(state.messages), {"msg-1", "msg-2"})
        self.assertEqual(state.messages["msg-1"].body_text, "Body text fo")
        self.assertEqual(state.messages["msg-2"].body_text, "Thread reply")

    def test_sync_mailbox_from_gmail_limits_thread_context_messages(self) -> None:
        state = MailwyrmState()
        client = FakeSyncClient()
        client.message_refs = [{"id": "msg-3", "threadId": "thread-1"}]
        client.thread_messages = [
            client._full_message("msg-1"),
            client._full_message("msg-2", body="VHdv"),
            client._full_message("msg-3", body="VGhyZWU"),
            client._full_message("msg-4", body="Rm91cg"),
        ]

        stats = sync_mailbox_from_gmail(
            client,
            state,
            limit=10,
            mailbox="inbox",
            include_body=True,
            include_thread_context=True,
            thread_context_limit=2,
        )

        self.assertEqual(stats.selected_message_refs, 1)
        self.assertEqual(set(state.messages), {"msg-2", "msg-3"})
        self.assertNotIn("msg-1", state.messages)
        self.assertNotIn("msg-4", state.messages)

    def test_sync_mailbox_from_gmail_rejects_non_positive_thread_context_limit(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            sync_mailbox_from_gmail(
                FakeSyncClient(),
                MailwyrmState(),
                limit=10,
                mailbox="inbox",
                include_body=True,
                include_thread_context=True,
                thread_context_limit=0,
            )

    def test_sync_mailbox_from_gmail_rejects_thread_context_without_body(self) -> None:
        with self.assertRaises(ValueError):
            sync_mailbox_from_gmail(
                FakeSyncClient(),
                MailwyrmState(),
                limit=10,
                mailbox="inbox",
                include_thread_context=True,
            )

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

    def test_reconcile_history_fetches_new_messages_from_history(self) -> None:
        state = MailwyrmState(history_id="100")
        client = FakeSyncClient()

        stats = reconcile_history(
            state,
            {
                "historyId": "105",
                "history": [
                    {
                        "messagesAdded": [
                            {"message": {"id": "msg-2"}},
                        ],
                    }
                ],
            },
            client=client,
            include_body=True,
            body_char_limit=9,
        )

        self.assertIn("msg-2", state.messages)
        self.assertEqual(state.messages["msg-2"].body_text, "Body text")
        self.assertEqual(client.full_message_ids, ["msg-2"])
        self.assertEqual(stats.messages_fetched, 1)
        self.assertEqual(stats.fetched_message_ids, frozenset({"msg-2"}))
        self.assertEqual(stats.unknown_messages, 0)
        self.assertEqual(state.history_id, "105")

    def test_reconcile_history_fetches_unknown_label_events_when_client_is_available(
        self,
    ) -> None:
        state = MailwyrmState()
        client = FakeSyncClient()

        stats = reconcile_history(
            state,
            {
                "history": [
                    {
                        "labelsAdded": [
                            {"message": {"id": "msg-2"}, "labelIds": ["INBOX"]},
                        ],
                    }
                ],
            },
            client=client,
        )

        self.assertIn("msg-2", state.messages)
        self.assertEqual(client.metadata_message_ids, ["msg-2"])
        self.assertEqual(stats.messages_fetched, 1)
        self.assertEqual(stats.fetched_message_ids, frozenset({"msg-2"}))
        self.assertEqual(stats.unknown_messages, 0)

    def test_merge_history_stats_deduplicates_unknown_messages(self) -> None:
        merged = merge_history_stats(
            HistoryReconcileStats(
                history_records=1,
                messages_fetched=1,
                fetched_message_ids=frozenset({"msg-1"}),
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
        self.assertEqual(merged.messages_fetched, 1)
        self.assertEqual(merged.fetched_message_ids, frozenset({"msg-1"}))
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
            "Fetched messages: 0; Label changes: 3; deleted messages: 1; unknown messages: 4; "
            "cursor: advanced.",
        )


class FakeSyncClient:
    def __init__(self) -> None:
        self.metadata_message_ids: list[str] = []
        self.full_message_ids: list[str] = []
        self.thread_ids: list[str] = []
        self.list_kwargs = {}
        self.message_refs = [{"id": "msg-1"}]
        self.thread_messages = None

    def profile(self):
        return {"emailAddress": "user@example.com", "historyId": "42"}

    def list_messages(self, **kwargs):
        self.list_kwargs = kwargs
        return self.message_refs

    def get_message_metadata(self, message_id):
        self.metadata_message_ids.append(message_id)
        return self._message(message_id)

    def get_message_full(self, message_id):
        self.full_message_ids.append(message_id)
        return self._full_message(message_id)

    def get_thread_full(self, thread_id):
        self.thread_ids.append(thread_id)
        return {
            "id": thread_id,
            "messages": self.thread_messages
            or [
                self._full_message("msg-1"),
                self._full_message("msg-2", body="VGhyZWFkIHJlcGx5IGJvZHk"),
            ],
        }

    def _full_message(self, message_id, body="Qm9keSB0ZXh0IGZvciBjbGFzc2lmaWNhdGlvbg"):
        return {
            **self._message(message_id),
            "payload": {
                "headers": [{"name": "Subject", "value": "Hello"}],
                "mimeType": "text/plain",
                "body": {"data": body},
            },
        }

    def _message(self, message_id="msg-1"):
        return {
            "id": message_id,
            "threadId": "thread-1",
            "historyId": "10",
            "internalDate": "1710000000000",
            "labelIds": ["INBOX"],
            "snippet": "Snippet",
            "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
        }


if __name__ == "__main__":
    unittest.main()
