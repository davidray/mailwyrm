from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_METADATA_HEADERS = ("From", "To", "Subject", "Date", "Message-ID")


@dataclass(frozen=True)
class GmailToken:
    access_token: str
    expires_at: float
    scope: str
    token_type: str = "Bearer"
    refresh_token: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GmailToken":
        return cls(
            access_token=str(data["access_token"]),
            expires_at=float(data["expires_at"]),
            scope=str(data.get("scope", "")),
            token_type=str(data.get("token_type", "Bearer")),
            refresh_token=data.get("refresh_token"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MessageRecord:
    id: str
    thread_id: str
    history_id: str | None
    internal_date: str | None
    label_ids: list[str]
    snippet: str
    headers: dict[str, str]

    @classmethod
    def from_gmail_message(cls, message: dict[str, Any]) -> "MessageRecord":
        payload = message.get("payload") or {}
        raw_headers = payload.get("headers") or []
        headers = {
            str(header.get("name")): str(header.get("value", ""))
            for header in raw_headers
            if header.get("name")
        }

        return cls(
            id=str(message["id"]),
            thread_id=str(message["threadId"]),
            history_id=message.get("historyId"),
            internal_date=message.get("internalDate"),
            label_ids=[str(label) for label in message.get("labelIds", [])],
            snippet=str(message.get("snippet", "")),
            headers=headers,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageRecord":
        return cls(
            id=str(data["id"]),
            thread_id=str(data["thread_id"]),
            history_id=data.get("history_id"),
            internal_date=data.get("internal_date"),
            label_ids=[str(label) for label in data.get("label_ids", [])],
            snippet=str(data.get("snippet", "")),
            headers={str(key): str(value) for key, value in data.get("headers", {}).items()},
        )

