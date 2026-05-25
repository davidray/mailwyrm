import tempfile
import unittest
from pathlib import Path

from mailwyrm.models import MessageRecord
from mailwyrm.store import MailwyrmState, read_state, write_state


class StoreTest(unittest.TestCase):
    def test_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            state = MailwyrmState(
                account_email="user@example.com",
                history_id="123",
                messages={
                    "msg-1": MessageRecord(
                        id="msg-1",
                        thread_id="thread-1",
                        history_id="10",
                        internal_date="1710000000000",
                        label_ids=["INBOX"],
                        snippet="A short snippet",
                        headers={"Subject": "Hello"},
                    )
                },
            )

            write_state(path, state)
            loaded = read_state(path)

        self.assertEqual(loaded.account_email, "user@example.com")
        self.assertEqual(loaded.history_id, "123")
        self.assertEqual(loaded.messages["msg-1"].headers["Subject"], "Hello")


if __name__ == "__main__":
    unittest.main()
