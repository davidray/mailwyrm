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
    actions_restore_archive_command,
    digest_command,
    digest_labels_apply_command,
    ensure_labels_command,
    labels_apply_command,
)
from mailwyrm.models import (
    GMAIL_MODIFY_SCOPE,
    GMAIL_READONLY_SCOPE,
    ClassificationRecord,
    DigestAuditEvent,
    GmailToken,
    MessageRecord,
)
from mailwyrm.store import MailwyrmState, write_state, write_token


class CliTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
