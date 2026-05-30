import unittest

from mailwyrm.models import MessageRecord


class MessageRecordTest(unittest.TestCase):
    def test_message_record_from_gmail_metadata(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "historyId": "42",
            "internalDate": "1710000000000",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "hello there",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Ada <ada@example.com>"},
                    {"name": "Subject", "value": "Hello"},
                ]
            },
        }

        record = MessageRecord.from_gmail_message(message)

        self.assertEqual(record.id, "msg-1")
        self.assertEqual(record.thread_id, "thread-1")
        self.assertEqual(record.history_id, "42")
        self.assertEqual(record.label_ids, ["INBOX", "UNREAD"])
        self.assertEqual(record.headers["From"], "Ada <ada@example.com>")
        self.assertEqual(record.headers["Subject"], "Hello")

    def test_message_record_decodes_html_entities_in_gmail_snippet(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Elder Christiansen&#39;s account &amp; correspondence",
            "payload": {"headers": []},
        }

        record = MessageRecord.from_gmail_message(message)

        self.assertEqual(
            record.snippet,
            "Elder Christiansen's account & correspondence",
        )

    def test_message_record_canonicalizes_uppercase_gmail_headers(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "headers": [
                    {
                        "name": "FROM",
                        "value": "Lucy Cavendish College <development@lucy.cam.ac.uk>",
                    },
                    {"name": "TO", "value": "Dave <dave@example.com>"},
                ]
            },
        }

        record = MessageRecord.from_gmail_message(message)

        self.assertEqual(
            record.headers["From"],
            "Lucy Cavendish College <development@lucy.cam.ac.uk>",
        )
        self.assertEqual(record.headers["To"], "Dave <dave@example.com>")
        self.assertNotIn("FROM", record.headers)

    def test_message_record_decodes_html_entities_from_local_state(self) -> None:
        record = MessageRecord.from_dict(
            {
                "id": "msg-1",
                "thread_id": "thread-1",
                "snippet": "Please check Elder Christiansen&#39;s account.",
            }
        )

        self.assertEqual(
            record.snippet,
            "Please check Elder Christiansen's account.",
        )

    def test_message_record_canonicalizes_uppercase_headers_from_local_state(self) -> None:
        record = MessageRecord.from_dict(
            {
                "id": "msg-1",
                "thread_id": "thread-1",
                "headers": {
                    "FROM": "Lucy Cavendish College <development@lucy.cam.ac.uk>",
                    "TO": "Dave <dave@example.com>",
                },
            }
        )

        self.assertEqual(
            record.headers["From"],
            "Lucy Cavendish College <development@lucy.cam.ac.uk>",
        )
        self.assertEqual(record.headers["To"], "Dave <dave@example.com>")
        self.assertNotIn("FROM", record.headers)

    def test_message_record_removes_tracking_urls_from_local_text(self) -> None:
        record = MessageRecord.from_dict(
            {
                "id": "msg-1",
                "thread_id": "thread-1",
                "snippet": (
                    "Legacy Village Hello Doris Peck! "
                    "<https://s22aeml01blkbs02.blob.core.windows.net/emailimages/"
                    "2026/5/some-very-long-tracking-image-reference.png>"
                ),
                "body_text": (
                    "<https://s22aeml01blkbs02.blob.core.windows.net/emailimages/"
                    "2026/5/some-very-long-tracking-image-reference.png>\n"
                    "News <https://eml-peur01.app.blackbaud.net/intv2/j/"
                    "D9D3D6FF-EC69-451F-9461-1C10D25FB1FA/r/link>\n"
                    "The President's Monthly Message"
                ),
            }
        )

        self.assertEqual(record.snippet, "Legacy Village Hello Doris Peck!")
        self.assertEqual(
            record.body_text,
            "News\nThe President's Monthly Message",
        )

    def test_message_record_preserves_markdown_links_for_rendering(self) -> None:
        record = MessageRecord.from_dict(
            {
                "id": "msg-1",
                "thread_id": "thread-1",
                "body_text": (
                    "# Hi DAVID\n"
                    "Click here to pay: [Pay now](https://buy.stripe.com/test)"
                ),
            }
        )

        self.assertEqual(
            record.body_text,
            "# Hi DAVID\nClick here to pay: [Pay now](https://buy.stripe.com/test)",
        )

    def test_message_record_extracts_bounded_plain_body_text(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "SGVsbG8gRWxkZXIgQ2hyaXN0aWFuc2VuJ3MgYWNjb3VudA"},
                    }
                ],
            },
        }

        record = MessageRecord.from_gmail_message(message, body_char_limit=12)

        self.assertEqual(record.body_text, "Hello Elder ")

    def test_message_record_uses_html_body_when_plain_text_is_unavailable(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "text/html",
                "headers": [],
                "body": {
                    "data": "PHA-RGVsaXZlcnkgPHN0cm9uZz51cGRhdGU8L3N0cm9uZz48YnI-RnJpZGF5PC9wPg"
                },
            },
        }

        record = MessageRecord.from_gmail_message(message, body_char_limit=100)

        self.assertEqual(record.body_text, "Delivery update\nFriday")

    def test_message_record_ignores_script_style_and_head_html_text(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "text/html",
                "headers": [],
                "body": {
                    "data": (
                        "PGh0bWw-PGhlYWQ-PHRpdGxlPk5vdCBtYWlsPC90aXRsZT48c3R5bGU-"
                        "LmEge308PC9zdHlsZT48L2hlYWQ-PGJvZHk-PHNjcmlwdD5ldmlsKCk8"
                        "L3NjcmlwdD48cD5SZWFsIG1lc3NhZ2U8L3A-PC9ib2R5PjwvaHRtbD4"
                    )
                },
            },
        }

        record = MessageRecord.from_gmail_message(message, body_char_limit=100)

        self.assertEqual(record.body_text, "Real message")

    def test_message_record_ignores_malformed_body_payloads(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"data": "abcde"},
            },
        }

        record = MessageRecord.from_gmail_message(message, body_char_limit=100)

        self.assertEqual(record.body_text, "")

    def test_message_record_does_not_fetch_attachment_body_parts_yet(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"attachmentId": "ATTACHMENT_1"},
            },
        }

        record = MessageRecord.from_gmail_message(message, body_char_limit=100)

        self.assertEqual(record.body_text, "")

    def test_message_record_does_not_extract_body_without_limit(self) -> None:
        message = {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"data": "SGVsbG8"},
            },
        }

        record = MessageRecord.from_gmail_message(message)

        self.assertEqual(record.body_text, "")


if __name__ == "__main__":
    unittest.main()
