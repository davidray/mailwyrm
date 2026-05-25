import unittest

from mailwyrm.cli import label_ids_for_mailbox


class SyncMailboxTest(unittest.TestCase):
    def test_label_ids_for_mailbox(self) -> None:
        self.assertEqual(label_ids_for_mailbox("inbox"), ("INBOX",))
        self.assertIsNone(label_ids_for_mailbox("all-mail"))


if __name__ == "__main__":
    unittest.main()
