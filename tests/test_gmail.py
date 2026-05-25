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


if __name__ == "__main__":
    unittest.main()
