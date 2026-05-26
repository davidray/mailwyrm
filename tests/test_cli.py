import os
import sys
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mailwyrm.cli import (
    actions_apply_archive_command,
    actions_apply_trash_command,
    actions_command,
    actions_restore_archive_command,
    actions_restore_trash_command,
    build_parser,
    daily_apply_command,
    daily_command,
    daily_cockpit_command,
    daily_status_command,
    digest_command,
    digest_labels_apply_command,
    ensure_labels_command,
    labels_apply_command,
    list_command,
    message_matches_mailbox,
    policy_command,
    policy_enable_trash_after_digest_command,
    sync_command,
)
from mailwyrm.models import (
    AutomationPolicy,
    GMAIL_MODIFY_SCOPE,
    GMAIL_READONLY_SCOPE,
    ClassificationRecord,
    DigestAuditEvent,
    GmailToken,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState, read_state, write_state, write_token


class CliTest(unittest.TestCase):
    def test_sync_command_fetches_metadata_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_READONLY_SCOPE,
                    ),
                )
                client = FakeSyncGmailClient()

                with patch("mailwyrm.cli.GmailClient", return_value=client):
                    with patch.object(sys, "stdout", StringIO()):
                        result = sync_command(Path("client_secret.json"), 1, "inbox")

                state = read_state(Path(temp_dir) / "state.json")

        self.assertEqual(result, 0)
        self.assertEqual(client.metadata_message_ids, ["msg-1"])
        self.assertEqual(client.full_message_ids, [])
        self.assertEqual(state.messages["msg-1"].body_text, "")

    def test_sync_command_preserves_body_text_during_metadata_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_READONLY_SCOPE,
                    ),
                )
                write_state(
                    state_path,
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                                body_text="Previously fetched body.",
                            )
                        }
                    ),
                )
                client = FakeSyncGmailClient()

                with patch("mailwyrm.cli.GmailClient", return_value=client):
                    with patch.object(sys, "stdout", StringIO()) as stdout:
                        result = sync_command(Path("client_secret.json"), 1, "inbox")

                state = read_state(state_path)

        self.assertEqual(result, 0)
        self.assertEqual(state.messages["msg-1"].body_text, "Previously fetched body.")
        self.assertIn("unchanged: 1", stdout.getvalue())

    def test_sync_command_can_fetch_bounded_body_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_READONLY_SCOPE,
                    ),
                )
                client = FakeSyncGmailClient()

                with patch("mailwyrm.cli.GmailClient", return_value=client):
                    with patch.object(sys, "stdout", StringIO()) as stdout:
                        result = sync_command(
                            Path("client_secret.json"),
                            1,
                            "inbox",
                            include_body=True,
                            body_char_limit=9,
                        )

                state = read_state(Path(temp_dir) / "state.json")

        self.assertEqual(result, 0)
        self.assertEqual(client.metadata_message_ids, [])
        self.assertEqual(client.full_message_ids, ["msg-1"])
        self.assertEqual(state.messages["msg-1"].body_text, "Body text")
        self.assertIn("Stored up to 9 body character", stdout.getvalue())

    def test_daily_cockpit_parser_rejects_negative_limits(self) -> None:
        parser = build_parser()

        with patch.object(sys, "stderr", StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["daily", "cockpit", "--limit", "-1"])

            with self.assertRaises(SystemExit):
                parser.parse_args(["daily", "cockpit", "--audit-limit", "-1"])

    def test_ensure_labels_requires_modify_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_READONLY_SCOPE,
                    ),
                )

                with patch.object(sys, "stderr", StringIO()) as stderr:
                    result = ensure_labels_command(Path("client_secret.json"))

        self.assertEqual(result, 1)
        self.assertIn("gmail.modify", stderr.getvalue())

    def test_policy_status_prints_local_policy_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_state(Path(temp_dir) / "state.json", MailwyrmState())

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = policy_command(Namespace(policy_command="status"))

        self.assertEqual(result, 0)
        self.assertIn("# Mailwyrm Policy Status", stdout.getvalue())
        self.assertIn("Archive after digest: enabled", stdout.getvalue())
        self.assertIn("Trash after digest: disabled", stdout.getvalue())

    def test_enable_trash_policy_requires_confirmation(self) -> None:
        with patch.object(sys, "stderr", StringIO()) as stderr:
            result = policy_enable_trash_after_digest_command(False)

        self.assertEqual(result, 1)
        self.assertIn("--confirm-trash-policy", stderr.getvalue())

    def test_enable_trash_policy_updates_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_state(state_path, MailwyrmState())

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = policy_enable_trash_after_digest_command(True)
                from mailwyrm.store import read_state

                loaded = read_state(state_path)

        self.assertEqual(result, 0)
        self.assertTrue(loaded.automation_policy.trash_after_digest_enabled)
        self.assertIn("Trash after digest: enabled", stdout.getvalue())

    def test_actions_preview_trash_prints_policy_gated_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Promo"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="low",
                                automation_safety="high",
                                confidence=0.94,
                                reason="Low-risk promotion.",
                                suggested_actions=["digest", "trash"],
                                classifier_version="rules-v0",
                            )
                        },
                        digest_audit_events=[
                            DigestAuditEvent(
                                message_id="msg-1",
                                digest_title_date="2026-05-25",
                                reason="Low-risk promotion.",
                                classifier_version="rules-v0",
                                created_at="2026-05-25T00:00:00+00:00",
                            )
                        ],
                        automation_policy=AutomationPolicy(
                            trash_after_digest_enabled=True,
                        ),
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = actions_command(
                        Namespace(
                            actions_command="preview-trash",
                            limit=10,
                            mailbox="inbox",
                        )
                    )

        self.assertEqual(result, 0)
        self.assertIn("Mailbox Trash Preview", stdout.getvalue())
        self.assertIn("Trash policy: enabled", stdout.getvalue())
        self.assertIn("msg-1\ttrash_after_digest\tmachine\t0.94\tPromo", stdout.getvalue())

    def test_list_command_filters_by_trash_mailbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["TRASH"],
                                snippet="Snippet",
                                headers={
                                    "From": "sender@example.com",
                                    "Subject": "Trashed",
                                },
                            ),
                            "msg-2": MessageRecord(
                                id="msg-2",
                                thread_id="thread-2",
                                history_id="11",
                                internal_date="1710000000001",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={
                                    "From": "sender@example.com",
                                    "Subject": "Inbox",
                                },
                            ),
                        },
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = list_command(25, False, "trash")

        self.assertEqual(result, 0)
        self.assertIn("msg-1\tsender@example.com\tTrashed", stdout.getvalue())
        self.assertNotIn("msg-2", stdout.getvalue())

    def test_message_matches_mailbox(self) -> None:
        inbox_message = MessageRecord(
            id="msg-1",
            thread_id="thread-1",
            history_id="10",
            internal_date="1710000000000",
            label_ids=["INBOX"],
            snippet="Snippet",
            headers={},
        )
        trash_message = MessageRecord(
            id="msg-2",
            thread_id="thread-2",
            history_id="11",
            internal_date="1710000000001",
            label_ids=["TRASH"],
            snippet="Snippet",
            headers={},
        )

        self.assertTrue(message_matches_mailbox(inbox_message, "inbox"))
        self.assertTrue(message_matches_mailbox(inbox_message, "all-mail"))
        self.assertFalse(message_matches_mailbox(inbox_message, "trash"))
        self.assertTrue(message_matches_mailbox(trash_message, "trash"))

    def test_labels_apply_prints_preview_report_before_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.apply_label_plans", return_value=1):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = labels_apply_command(
                                Path("client_secret.json"),
                                1,
                                "inbox",
                            )

        self.assertEqual(result, 0)
        self.assertIn("Message ID\tLabels\tSubject", stdout.getvalue())
        self.assertIn("msg-1\tMailwyrm/Machine\tHello", stdout.getvalue())
        self.assertIn("Applied Gmail labels to 1 message(s).", stdout.getvalue())

    def test_digest_marks_included_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_state(
                    state_path,
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    with patch("mailwyrm.cli.datetime") as fake_datetime:
                        fake_datetime.now.return_value.date.return_value.isoformat.return_value = (
                            "2026-05-25"
                        )
                        result = digest_command(
                            Namespace(digest_command=None, output=None)
                        )
                from mailwyrm.store import read_state

                loaded = read_state(state_path)

        self.assertEqual(result, 0)
        self.assertIn("Marked 1 message(s) as digested.", stdout.getvalue())
        self.assertIn("# Mailwyrm Machine Digest - 2026-05-25", stdout.getvalue())
        self.assertEqual(loaded.digest_audit_events[0].message_id, "msg-1")
        self.assertEqual(loaded.digest_audit_events[0].digest_title_date, "2026-05-25")

    def test_daily_cockpit_prints_read_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        account_email="user@example.com",
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    with patch("mailwyrm.cli.datetime") as fake_datetime:
                        fake_datetime.now.return_value.date.return_value.isoformat.return_value = (
                            "2026-05-25"
                        )
                        result = daily_cockpit_command(1, "inbox", 5)
                from mailwyrm.store import read_state

                loaded = read_state(Path(temp_dir) / "state.json")

        self.assertEqual(result, 0)
        self.assertIn("# Mailwyrm Daily Cockpit - 2026-05-25", stdout.getvalue())
        self.assertIn("Read-only local view.", stdout.getvalue())
        self.assertIn("## Machine Digest", stdout.getvalue())
        self.assertIn("## Mailbox Actions", stdout.getvalue())
        self.assertEqual(loaded.digest_audit_events, [])

    def test_daily_preview_prints_combined_report_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_state(
                    state_path,
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    with patch("mailwyrm.cli.datetime") as fake_datetime:
                        fake_datetime.now.return_value.date.return_value.isoformat.return_value = (
                            "2026-05-25"
                        )
                        result = daily_command(
                            Namespace(
                                daily_command="preview",
                                limit=1,
                                mailbox="inbox",
                            )
                        )
                from mailwyrm.store import read_state

                loaded = read_state(state_path)

        self.assertEqual(result, 0)
        self.assertIn("# Mailwyrm Daily Preview - 2026-05-25", stdout.getvalue())
        self.assertIn("## Machine Digest", stdout.getvalue())
        self.assertIn("## Gmail Digested Labels", stdout.getvalue())
        self.assertIn("## Mailbox Actions", stdout.getvalue())
        self.assertEqual(loaded.digest_audit_events, [])

    def test_daily_apply_prints_report_then_marks_labels_and_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    state_path,
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.apply_digested_label_plans", return_value=1):
                        from mailwyrm.actions import ArchiveApplyResult

                        with patch(
                            "mailwyrm.cli.apply_archive_action_plans",
                            return_value=ArchiveApplyResult(applied=1),
                        ):
                            with patch.object(sys, "stdout", StringIO()) as stdout:
                                with patch("mailwyrm.cli.datetime") as fake_datetime:
                                    fake_datetime.now.return_value.date.return_value.isoformat.return_value = (
                                        "2026-05-25"
                                    )
                                    result = daily_apply_command(
                                        Path("client_secret.json"),
                                        1,
                                        "inbox",
                                    )
                from mailwyrm.store import read_state

                loaded = read_state(state_path)

        self.assertEqual(result, 0)
        self.assertIn("# Mailwyrm Daily Preview - 2026-05-25", stdout.getvalue())
        self.assertIn("Gmail will be modified after this preview.", stdout.getvalue())
        self.assertIn("msg-1\tMailwyrm/Digested\tHello", stdout.getvalue())
        self.assertIn("Marked 1 message(s) as digested.", stdout.getvalue())
        self.assertIn(
            "Applied Mailwyrm/Digested label to 1 message(s).",
            stdout.getvalue(),
        )
        self.assertIn(
            "Archived 1 message(s) by removing Gmail's INBOX label.",
            stdout.getvalue(),
        )
        self.assertIn("Trash actions were not applied.", stdout.getvalue())
        self.assertEqual(len(loaded.digest_audit_events), 1)
        self.assertEqual(loaded.digest_audit_events[0].message_id, "msg-1")

    def test_daily_apply_persists_digested_labels_before_archive_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                state_path = Path(temp_dir) / "state.json"
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    state_path,
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                def apply_digested(_client, state, _plans):
                    from mailwyrm.models import LabelAuditEvent

                    state.label_audit_events.append(
                        LabelAuditEvent(
                            message_id="msg-1",
                            action="add_digested_label",
                            label_names=["Mailwyrm/Digested"],
                            label_ids=["label-digested"],
                            reason="Automated sender or subject pattern.",
                            classifier_version="rules-v0",
                            created_at="2026-05-25T00:00:00+00:00",
                        )
                    )
                    return 1

                with patch("mailwyrm.cli.GmailClient"):
                    with patch(
                        "mailwyrm.cli.apply_digested_label_plans",
                        side_effect=apply_digested,
                    ):
                        with patch(
                            "mailwyrm.cli.apply_archive_action_plans",
                            side_effect=RuntimeError("archive failed"),
                        ):
                            with patch.object(sys, "stdout", StringIO()):
                                with patch("mailwyrm.cli.datetime") as fake_datetime:
                                    fake_datetime.now.return_value.date.return_value.isoformat.return_value = (
                                        "2026-05-25"
                                    )
                                    with self.assertRaises(RuntimeError):
                                        daily_apply_command(
                                            Path("client_secret.json"),
                                            1,
                                            "inbox",
                                        )
                from mailwyrm.store import read_state

                loaded = read_state(state_path)

        self.assertEqual(len(loaded.digest_audit_events), 1)
        self.assertEqual(len(loaded.label_audit_events), 1)
        self.assertEqual(loaded.label_audit_events[0].action, "add_digested_label")

    def test_daily_status_prints_local_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        account_email="user@example.com",
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = daily_status_command("inbox")

        self.assertEqual(result, 0)
        self.assertIn("# Mailwyrm Daily Status", stdout.getvalue())
        self.assertIn("Account: user@example.com", stdout.getvalue())
        self.assertIn("Archive after digest: 1", stdout.getvalue())

    def test_actions_apply_archive_prints_preview_report_before_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="medium",
                                automation_safety="medium",
                                confidence=0.82,
                                reason="Automated sender or subject pattern.",
                                suggested_actions=["digest"],
                                classifier_version="rules-v0",
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    from mailwyrm.actions import ArchiveApplyResult

                    with patch(
                        "mailwyrm.cli.apply_archive_action_plans",
                        return_value=ArchiveApplyResult(
                            applied=1,
                            skipped_not_digested=2,
                        ),
                    ):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = actions_apply_archive_command(
                                Path("client_secret.json"),
                                1,
                                "inbox",
                            )

        self.assertEqual(result, 0)
        self.assertIn("Mailbox Action Preview", stdout.getvalue())
        self.assertIn("Gmail will be modified after this preview.", stdout.getvalue())
        self.assertNotIn("No Gmail actions will be performed.", stdout.getvalue())
        self.assertIn("msg-1\tarchive_after_digest\tmachine\t0.82\tHello", stdout.getvalue())
        self.assertIn(
            "Archived 1 message(s) by removing Gmail's INBOX label.",
            stdout.getvalue(),
        )
        self.assertIn(
            "Skipped 2 archive candidate(s) because they have not appeared in a digest yet.",
            stdout.getvalue(),
        )

    def test_actions_apply_trash_prints_preview_report_before_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Promo"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="low",
                                automation_safety="high",
                                confidence=0.94,
                                reason="Low-risk promotion.",
                                suggested_actions=["digest", "trash"],
                                classifier_version="rules-v0",
                            )
                        },
                        digest_audit_events=[
                            DigestAuditEvent(
                                message_id="msg-1",
                                digest_title_date="2026-05-25",
                                reason="Low-risk promotion.",
                                classifier_version="rules-v0",
                                created_at="2026-05-25T00:00:00+00:00",
                            )
                        ],
                        automation_policy=AutomationPolicy(
                            trash_after_digest_enabled=True,
                        ),
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    from mailwyrm.actions import TrashApplyResult

                    with patch(
                        "mailwyrm.cli.apply_trash_action_preview",
                        return_value=TrashApplyResult(applied=1),
                    ):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = actions_apply_trash_command(
                                Path("client_secret.json"),
                                1,
                                "inbox",
                            )

        self.assertEqual(result, 0)
        self.assertIn("Mailbox Trash Preview", stdout.getvalue())
        self.assertIn("Gmail will be modified after this preview.", stdout.getvalue())
        self.assertIn("msg-1\ttrash_after_digest\tmachine\t0.94\tPromo", stdout.getvalue())
        self.assertIn(
            "Trashed 1 message(s) using Gmail's trash operation.",
            stdout.getvalue(),
        )

    def test_actions_apply_trash_reports_disabled_policy_without_gmail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Promo"},
                            )
                        },
                        classifications={
                            "msg-1": ClassificationRecord(
                                message_id="msg-1",
                                category="machine",
                                machine_type="notification",
                                importance="low",
                                automation_safety="high",
                                confidence=0.94,
                                reason="Low-risk promotion.",
                                suggested_actions=["digest", "trash"],
                                classifier_version="rules-v0",
                            )
                        },
                        digest_audit_events=[
                            DigestAuditEvent(
                                message_id="msg-1",
                                digest_title_date="2026-05-25",
                                reason="Low-risk promotion.",
                                classifier_version="rules-v0",
                                created_at="2026-05-25T00:00:00+00:00",
                            )
                        ],
                    ),
                )

                with patch("mailwyrm.cli.GmailClient") as gmail_client:
                    with patch.object(sys, "stdout", StringIO()) as stdout:
                        result = actions_apply_trash_command(
                            Path("client_secret.json"),
                            1,
                            "inbox",
                        )

        self.assertEqual(result, 0)
        gmail_client.assert_not_called()
        self.assertIn("Trash policy: disabled", stdout.getvalue())
        self.assertIn(
            "Trash policy is disabled; no Gmail trash actions were applied.",
            stdout.getvalue(),
        )

    def test_actions_audit_prints_local_audit_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                from mailwyrm.models import LabelAuditEvent

                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["TRASH"],
                                snippet="Snippet",
                                headers={"Subject": "Promo"},
                            )
                        },
                        label_audit_events=[
                            LabelAuditEvent(
                                message_id="msg-1",
                                action="trash_after_digest",
                                label_names=["TRASH"],
                                label_ids=["TRASH"],
                                reason="Low-risk promotion.",
                                classifier_version="rules-v0",
                                created_at="2026-05-25T00:00:00+00:00",
                            )
                        ],
                    ),
                )

                with patch.object(sys, "stdout", StringIO()) as stdout:
                    result = actions_command(
                        Namespace(actions_command="audit", limit=25)
                    )

        self.assertEqual(result, 0)
        self.assertIn("Mailbox Action Audit", stdout.getvalue())
        self.assertIn("msg-1\ttrash_after_digest\tTRASH\tPromo", stdout.getvalue())

    def test_digest_labels_apply_prints_preview_report_before_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                        digest_audit_events=[
                            DigestAuditEvent(
                                message_id="msg-1",
                                digest_title_date="2026-05-25",
                                reason="Automated sender or subject pattern.",
                                classifier_version="rules-v0",
                                created_at="2026-05-25T00:00:00+00:00",
                            )
                        ],
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.apply_digested_label_plans", return_value=1):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = digest_labels_apply_command(
                                Path("client_secret.json"),
                                1,
                            )

        self.assertEqual(result, 0)
        self.assertIn("Message ID\tLabels\tSubject", stdout.getvalue())
        self.assertIn("msg-1\tMailwyrm/Digested\tHello", stdout.getvalue())
        self.assertIn(
            "Applied Mailwyrm/Digested label to 1 message(s).",
            stdout.getvalue(),
        )

    def test_actions_restore_archive_restores_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=[],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.restore_archived_message", return_value=True):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = actions_restore_archive_command(
                                Path("client_secret.json"),
                                "msg-1",
                            )

        self.assertEqual(result, 0)
        self.assertIn(
            "Restored msg-1 to inbox by adding Gmail's INBOX label.",
            stdout.getvalue(),
        )

    def test_actions_restore_archive_reports_unknown_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(Path(temp_dir) / "state.json", MailwyrmState())

                with patch("mailwyrm.cli.GmailClient"):
                    with patch.object(sys, "stderr", StringIO()) as stderr:
                        result = actions_restore_archive_command(
                            Path("client_secret.json"),
                            "missing",
                        )

        self.assertEqual(result, 1)
        self.assertIn("not in the local index", stderr.getvalue())

    def test_actions_restore_trash_restores_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["TRASH"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.restore_trashed_message", return_value=True):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = actions_restore_trash_command(
                                Path("client_secret.json"),
                                "msg-1",
                            )

        self.assertEqual(result, 0)
        self.assertIn(
            "Restored msg-1 from trash to inbox by removing Gmail's TRASH label "
            "and adding INBOX.",
            stdout.getvalue(),
        )

    def test_actions_restore_trash_reports_non_trashed_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(
                    Path(temp_dir) / "state.json",
                    MailwyrmState(
                        messages={
                            "msg-1": MessageRecord(
                                id="msg-1",
                                thread_id="thread-1",
                                history_id="10",
                                internal_date="1710000000000",
                                label_ids=["INBOX"],
                                snippet="Snippet",
                                headers={"Subject": "Hello"},
                            )
                        },
                    ),
                )

                with patch("mailwyrm.cli.GmailClient"):
                    with patch("mailwyrm.cli.restore_trashed_message", return_value=False):
                        with patch.object(sys, "stdout", StringIO()) as stdout:
                            result = actions_restore_trash_command(
                                Path("client_secret.json"),
                                "msg-1",
                            )

        self.assertEqual(result, 0)
        self.assertIn("Message msg-1 is not in trash.", stdout.getvalue())

    def test_actions_restore_trash_reports_unknown_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"MAILWYRM_HOME": temp_dir}):
                write_token(
                    Path(temp_dir) / "gmail-token.json",
                    GmailToken(
                        access_token="token",
                        expires_at=9999999999,
                        scope=GMAIL_MODIFY_SCOPE,
                    ),
                )
                write_state(Path(temp_dir) / "state.json", MailwyrmState())

                with patch("mailwyrm.cli.GmailClient"):
                    with patch.object(sys, "stderr", StringIO()) as stderr:
                        result = actions_restore_trash_command(
                            Path("client_secret.json"),
                            "missing",
                        )

        self.assertEqual(result, 1)
        self.assertIn("not in the local index", stderr.getvalue())


class FakeSyncGmailClient:
    def __init__(self) -> None:
        self.metadata_message_ids = []
        self.full_message_ids = []

    def profile(self):
        return {"emailAddress": "user@example.com", "historyId": "42"}

    def list_messages(self, **kwargs):
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
