from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mailwyrm.models import GmailToken, MessageRecord


@dataclass
class MailwyrmState:
    account_email: str | None = None
    history_id: str | None = None
    messages: dict[str, MessageRecord] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MailwyrmState":
        messages = {
            message_id: MessageRecord.from_dict(message)
            for message_id, message in data.get("messages", {}).items()
        }
        return cls(
            account_email=data.get("account_email"),
            history_id=data.get("history_id"),
            messages=messages,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_email": self.account_email,
            "history_id": self.history_id,
            "messages": {
                message_id: message.to_dict()
                for message_id, message in sorted(self.messages.items())
            },
        }


def read_token(path: Path) -> GmailToken | None:
    if not path.exists():
        return None
    return GmailToken.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_token(path: Path, token: GmailToken) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, token.to_dict())
    path.chmod(0o600)


def read_state(path: Path) -> MailwyrmState:
    if not path.exists():
        return MailwyrmState()
    return MailwyrmState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_state(path: Path, state: MailwyrmState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, state.to_dict())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)

