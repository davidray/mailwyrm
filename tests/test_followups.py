import unittest

from mailwyrm.followups import (
    message_marked_read_later,
    message_needs_followup,
    set_followup,
    set_read_later,
)
from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState


def message(message_id: str) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        history_id="10",
        internal_date="1710000000000",
        label_ids=["INBOX"],
        snippet="Snippet.",
        headers={"Subject": "Digest item"},
    )


class FollowUpTest(unittest.TestCase):
    def test_sets_and_clears_followup_marker(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        marked = set_followup(
            state,
            message_ids=["msg-1"],
            followup=True,
            reason="Needs a response.",
        )

        self.assertEqual(marked["changed"], 1)
        self.assertTrue(message_needs_followup(state, "msg-1"))
        self.assertEqual(state.followups["msg-1"].reason, "Needs a response.")

        cleared = set_followup(state, message_ids=["msg-1"], followup=False)

        self.assertEqual(cleared["changed"], 1)
        self.assertFalse(message_needs_followup(state, "msg-1"))

    def test_rejects_unknown_message(self) -> None:
        with self.assertRaises(ValueError):
            set_followup(MailwyrmState(), message_ids=["missing"], followup=True)

    def test_sets_and_clears_read_later_marker(self) -> None:
        state = MailwyrmState(messages={"msg-1": message("msg-1")})

        marked = set_read_later(
            state,
            message_ids=["msg-1"],
            read_later=True,
            reason="Worth reading.",
        )

        self.assertEqual(marked["changed"], 1)
        self.assertTrue(message_marked_read_later(state, "msg-1"))
        self.assertEqual(state.read_later["msg-1"].reason, "Worth reading.")

        cleared = set_read_later(state, message_ids=["msg-1"], read_later=False)

        self.assertEqual(cleared["changed"], 1)
        self.assertFalse(message_marked_read_later(state, "msg-1"))


if __name__ == "__main__":
    unittest.main()
