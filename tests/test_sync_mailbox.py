import unittest

from mailwyrm.sync import include_spam_trash_for_mailbox, label_ids_for_mailbox


class SyncMailboxTest(unittest.TestCase):
    def test_label_ids_for_mailbox(self) -> None:
        self.assertEqual(label_ids_for_mailbox("inbox"), ("INBOX",))
        self.assertIsNone(label_ids_for_mailbox("all-mail"))
        self.assertEqual(label_ids_for_mailbox("trash"), ("TRASH",))

    def test_include_spam_trash_for_mailbox(self) -> None:
        self.assertFalse(include_spam_trash_for_mailbox("inbox"))
        self.assertFalse(include_spam_trash_for_mailbox("all-mail"))
        self.assertTrue(include_spam_trash_for_mailbox("trash"))


if __name__ == "__main__":
    unittest.main()
