import unittest

from mailwyrm.gmail import GmailClient, GmailLabel
from mailwyrm.models import GmailToken


class FakeGmailClient(GmailClient):
    def __init__(self, labels):
        super().__init__(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.modify",
            )
        )
        self.labels = list(labels)
        self.created_names = []

    def list_labels(self):
        return list(self.labels)

    def create_label(self, name):
        label = GmailLabel(id=f"id-{name}", name=name)
        self.created_names.append(name)
        self.labels.append(label)
        return label


class GmailClientTest(unittest.TestCase):
    def test_ensure_mailwyrm_labels_creates_missing_labels(self) -> None:
        client = FakeGmailClient([])

        labels = client.ensure_mailwyrm_labels()

        self.assertIn("Mailwyrm/Human", labels)
        self.assertIn("Mailwyrm/Protected", labels)
        self.assertIn("Mailwyrm/Human", client.created_names)

    def test_ensure_mailwyrm_labels_reuses_existing_labels(self) -> None:
        label = GmailLabel(id="existing", name="Mailwyrm/Human")
        client = FakeGmailClient([label])

        labels = client.ensure_mailwyrm_labels()

        self.assertEqual(labels["Mailwyrm/Human"].id, "existing")
        self.assertNotIn("Mailwyrm/Human", client.created_names)

    def test_add_labels_to_message_posts_modify_payload(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.modify",
            )
        )
        calls = []

        def fake_post(path, body):
            calls.append((path, body))
            return {}

        client._post = fake_post

        client.add_labels_to_message("msg 1/part", ["Label_1"])

        self.assertEqual(calls[0][0], "/users/me/messages/msg%201%2Fpart/modify")
        self.assertEqual(calls[0][1]["addLabelIds"], ["Label_1"])
        self.assertEqual(calls[0][1]["removeLabelIds"], [])

    def test_remove_labels_from_message_posts_modify_payload(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.modify",
            )
        )
        calls = []

        def fake_post(path, body):
            calls.append((path, body))
            return {}

        client._post = fake_post

        client.remove_labels_from_message("msg 1/part", ["INBOX"])

        self.assertEqual(calls[0][0], "/users/me/messages/msg%201%2Fpart/modify")
        self.assertEqual(calls[0][1]["addLabelIds"], [])
        self.assertEqual(calls[0][1]["removeLabelIds"], ["INBOX"])

    def test_modify_message_labels_posts_add_and_remove_payload(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.modify",
            )
        )
        calls = []

        def fake_post(path, body):
            calls.append((path, body))
            return {}

        client._post = fake_post

        client.modify_message_labels(
            "msg 1/part",
            add_label_ids=["INBOX"],
            remove_label_ids=["TRASH"],
        )

        self.assertEqual(calls[0][0], "/users/me/messages/msg%201%2Fpart/modify")
        self.assertEqual(calls[0][1]["addLabelIds"], ["INBOX"])
        self.assertEqual(calls[0][1]["removeLabelIds"], ["TRASH"])

    def test_trash_message_posts_trash_endpoint(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.modify",
            )
        )
        calls = []

        def fake_post(path, body):
            calls.append((path, body))
            return {}

        client._post = fake_post

        client.trash_message("msg 1/part")

        self.assertEqual(calls[0][0], "/users/me/messages/msg%201%2Fpart/trash")
        self.assertEqual(calls[0][1], {})

    def test_list_messages_omits_label_filter_when_label_ids_is_none(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.readonly",
            )
        )
        urls = []

        def fake_request(url, **kwargs):
            urls.append(url)
            return {"messages": []}

        client._request = fake_request

        client.list_messages(max_results=10, label_ids=None)

        self.assertIn("maxResults=10", urls[0])
        self.assertNotIn("labelIds=", urls[0])

    def test_list_messages_includes_inbox_label_by_default(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.readonly",
            )
        )
        urls = []

        def fake_request(url, **kwargs):
            urls.append(url)
            return {"messages": []}

        client._request = fake_request

        client.list_messages(max_results=10)

        self.assertIn("labelIds=INBOX", urls[0])

    def test_list_messages_can_include_spam_and_trash(self) -> None:
        client = GmailClient(
            GmailToken(
                access_token="token",
                expires_at=9999999999,
                scope="https://www.googleapis.com/auth/gmail.readonly",
            )
        )
        urls = []

        def fake_request(url, **kwargs):
            urls.append(url)
            return {"messages": []}

        client._request = fake_request

        client.list_messages(
            max_results=10,
            label_ids=("TRASH",),
            include_spam_trash=True,
        )

        self.assertIn("includeSpamTrash=true", urls[0])
        self.assertIn("labelIds=TRASH", urls[0])


if __name__ == "__main__":
    unittest.main()
