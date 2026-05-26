import unittest
from importlib import resources

from mailwyrm.app import _query_int, _query_mailbox, create_app_server


class AppTest(unittest.TestCase):
    def test_app_static_assets_are_packaged_with_mailwyrm(self) -> None:
        static_root = resources.files("mailwyrm").joinpath("static")

        self.assertIn("<title>Mailwyrm</title>", static_root.joinpath("index.html").read_text())
        self.assertIn("Daily cockpit", static_root.joinpath("index.html").read_text())
        self.assertIn("human-lane", static_root.joinpath("index.html").read_text())
        self.assertIn("review-lane", static_root.joinpath("index.html").read_text())
        self.assertIn("workflows", static_root.joinpath("index.html").read_text())
        self.assertIn("/api/daily-cockpit", static_root.joinpath("app.js").read_text())
        self.assertIn("copy-command", static_root.joinpath("app.js").read_text())
        self.assertIn("workflow-status", static_root.joinpath("app.js").read_text())

    def test_query_int_accepts_zero_and_positive_values(self) -> None:
        self.assertEqual(_query_int({"limit": ["0"]}, "limit", 25), 0)
        self.assertEqual(_query_int({"limit": ["10"]}, "limit", 25), 10)
        self.assertEqual(_query_int({}, "limit", 25), 25)

    def test_query_int_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            _query_int({"limit": ["-1"]}, "limit", 25)

        with self.assertRaises(ValueError):
            _query_int({"limit": ["many"]}, "limit", 25)

    def test_query_mailbox_accepts_supported_mailboxes(self) -> None:
        self.assertEqual(_query_mailbox({}, "inbox"), "inbox")
        self.assertEqual(
            _query_mailbox({"mailbox": ["all-mail"]}, "inbox"),
            "all-mail",
        )
        self.assertEqual(_query_mailbox({"mailbox": ["trash"]}, "inbox"), "trash")

    def test_query_mailbox_rejects_unknown_mailboxes(self) -> None:
        with self.assertRaises(ValueError):
            _query_mailbox({"mailbox": ["spam"]}, "inbox")

        with self.assertRaises(ValueError):
            create_app_server(mailbox="spam")
