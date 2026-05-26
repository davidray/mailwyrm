from __future__ import annotations

import base64
import binascii
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from html import unescape
from typing import Any


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
DEFAULT_METADATA_HEADERS = ("From", "To", "Subject", "Date", "Message-ID")

MAILWYRM_LABEL_NAMES = (
    "Mailwyrm/Human",
    "Mailwyrm/Machine",
    "Mailwyrm/Needs Review",
    "Mailwyrm/Digested",
    "Mailwyrm/Protected",
)


ClassificationCategory = str
Importance = str
AutomationSafety = str

CLASSIFICATION_CATEGORIES = ("human", "machine", "needs_review")
MACHINE_TYPES = (
    "marketing",
    "transactional",
    "news",
    "spam",
    "product_community",
)


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
    body_text: str = ""

    @classmethod
    def from_gmail_message(
        cls,
        message: dict[str, Any],
        *,
        body_char_limit: int = 0,
    ) -> "MessageRecord":
        if body_char_limit < 0:
            raise ValueError("body_char_limit must be non-negative")
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
            snippet=normalize_email_text(message.get("snippet", "")),
            headers=headers,
            body_text=extract_message_body_text(payload, char_limit=body_char_limit),
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
            snippet=normalize_email_text(data.get("snippet", "")),
            headers={str(key): str(value) for key, value in data.get("headers", {}).items()},
            body_text=normalize_email_text(data.get("body_text", "")),
        )


def normalize_email_text(value: Any) -> str:
    return unescape(str(value))


def extract_message_body_text(payload: dict[str, Any], *, char_limit: int) -> str:
    if char_limit <= 0:
        return ""

    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_body_parts(payload, plain_parts=plain_parts, html_parts=html_parts)
    parts = plain_parts or [_html_to_text(part) for part in html_parts]
    body_text = _normalize_body_text("\n\n".join(part for part in parts if part))
    return body_text[:char_limit]


def _collect_body_parts(
    part: dict[str, Any],
    *,
    plain_parts: list[str],
    html_parts: list[str],
) -> None:
    mime_type = str(part.get("mimeType", "")).lower()
    body = part.get("body") or {}
    data = body.get("data")
    if data and mime_type == "text/plain":
        plain_parts.append(_decode_gmail_body_data(str(data)))
    elif data and mime_type == "text/html":
        html_parts.append(_decode_gmail_body_data(str(data)))

    for child in part.get("parts") or []:
        if isinstance(child, dict):
            _collect_body_parts(
                child,
                plain_parts=plain_parts,
                html_parts=html_parts,
            )


def _decode_gmail_body_data(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{data}{padding}")
    except (binascii.Error, ValueError):
        return ""
    return normalize_email_text(decoded.decode("utf-8", errors="replace"))


def _html_to_text(html: str) -> str:
    parser = _BodyTextHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def _normalize_body_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


class _BodyTextHTMLParser(HTMLParser):
    _IGNORED_TAGS = {"head", "script", "style", "title"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"br", "div", "li", "p", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag in {"div", "li", "p", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._parts.append(data)

    def text(self) -> str:
        return normalize_email_text("".join(self._parts))


@dataclass(frozen=True)
class ClassificationRecord:
    message_id: str
    category: ClassificationCategory
    machine_type: str | None
    importance: Importance
    automation_safety: AutomationSafety
    confidence: float
    reason: str
    suggested_actions: list[str]
    classifier_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationRecord":
        return cls(
            message_id=str(data["message_id"]),
            category=str(data["category"]),
            machine_type=data.get("machine_type"),
            importance=str(data["importance"]),
            automation_safety=str(data["automation_safety"]),
            confidence=float(data["confidence"]),
            reason=str(data["reason"]),
            suggested_actions=[str(action) for action in data.get("suggested_actions", [])],
            classifier_version=str(data["classifier_version"]),
        )


@dataclass(frozen=True)
class ClassificationCorrection:
    message_id: str
    category: ClassificationCategory
    machine_type: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationCorrection":
        return cls(
            message_id=str(data["message_id"]),
            category=str(data["category"]),
            machine_type=data.get("machine_type"),
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True)
class LabelAuditEvent:
    message_id: str
    action: str
    label_names: list[str]
    label_ids: list[str]
    reason: str
    classifier_version: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabelAuditEvent":
        return cls(
            message_id=str(data["message_id"]),
            action=str(data["action"]),
            label_names=[str(label) for label in data.get("label_names", [])],
            label_ids=[str(label) for label in data.get("label_ids", [])],
            reason=str(data.get("reason", "")),
            classifier_version=str(data.get("classifier_version", "")),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class DigestAuditEvent:
    message_id: str
    digest_title_date: str
    reason: str
    classifier_version: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DigestAuditEvent":
        return cls(
            message_id=str(data["message_id"]),
            digest_title_date=str(data["digest_title_date"]),
            reason=str(data.get("reason", "")),
            classifier_version=str(data.get("classifier_version", "")),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class AutomationPolicy:
    archive_after_digest_enabled: bool = True
    trash_after_digest_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutomationPolicy":
        if not isinstance(data, dict):
            data = {}
        return cls(
            archive_after_digest_enabled=_policy_bool(
                data.get("archive_after_digest_enabled"),
                default=True,
            ),
            trash_after_digest_enabled=_policy_bool(
                data.get("trash_after_digest_enabled"),
                default=False,
            ),
        )


def _policy_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
