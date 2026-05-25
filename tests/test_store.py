import tempfile
import unittest
from pathlib import Path

from mailwyrm.models import (
    ClassificationCorrection,
    ClassificationRecord,
    MessageRecord,
)
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
                classifications={
                    "msg-1": ClassificationRecord(
                        message_id="msg-1",
                        category="human",
                        machine_type=None,
                        importance="medium",
                        automation_safety="low",
                        confidence=0.68,
                        reason="Reply-style subject suggests a human conversation.",
                        suggested_actions=["review"],
                        classifier_version="rules-v0",
                    )
                },
                corrections={
                    "msg-1": ClassificationCorrection(
                        message_id="msg-1",
                        category="machine",
                        machine_type="newsletter",
                        reason="Known newsletter.",
                    )
                },
            )

            write_state(path, state)
            loaded = read_state(path)
            mode = path.stat().st_mode & 0o777

        self.assertEqual(loaded.account_email, "user@example.com")
        self.assertEqual(loaded.history_id, "123")
        self.assertEqual(loaded.messages["msg-1"].headers["Subject"], "Hello")
        self.assertEqual(loaded.classifications["msg-1"].category, "human")
        self.assertEqual(loaded.corrections["msg-1"].machine_type, "newsletter")
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
