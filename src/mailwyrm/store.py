from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mailwyrm.models import (
    AutomationPolicy,
    ClassificationCorrection,
    ClassificationRecord,
    DigestAuditEvent,
    FollowUpMarker,
    GmailToken,
    LabelAuditEvent,
    MessageRecord,
    ReadLaterMarker,
)


@dataclass
class MailwyrmState:
    account_email: str | None = None
    history_id: str | None = None
    last_sync_mailbox: str | None = None
    messages: dict[str, MessageRecord] = field(default_factory=dict)
    classifications: dict[str, ClassificationRecord] = field(default_factory=dict)
    corrections: dict[str, ClassificationCorrection] = field(default_factory=dict)
    followups: dict[str, FollowUpMarker] = field(default_factory=dict)
    read_later: dict[str, ReadLaterMarker] = field(default_factory=dict)
    digest_audit_events: list[DigestAuditEvent] = field(default_factory=list)
    label_audit_events: list[LabelAuditEvent] = field(default_factory=list)
    automation_policy: AutomationPolicy = field(default_factory=AutomationPolicy)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MailwyrmState":
        messages = {
            message_id: MessageRecord.from_dict(message)
            for message_id, message in data.get("messages", {}).items()
        }
        classifications = {
            message_id: ClassificationRecord.from_dict(classification)
            for message_id, classification in data.get("classifications", {}).items()
        }
        corrections = {
            message_id: ClassificationCorrection.from_dict(correction)
            for message_id, correction in data.get("corrections", {}).items()
        }
        followups = {
            message_id: FollowUpMarker.from_dict(marker)
            for message_id, marker in data.get("followups", {}).items()
        }
        read_later = {
            message_id: ReadLaterMarker.from_dict(marker)
            for message_id, marker in data.get("read_later", {}).items()
        }
        label_audit_events = [
            LabelAuditEvent.from_dict(event)
            for event in data.get("label_audit_events", [])
        ]
        digest_audit_events = [
            DigestAuditEvent.from_dict(event)
            for event in data.get("digest_audit_events", [])
        ]
        automation_policy = AutomationPolicy.from_dict(
            data.get("automation_policy", {})
        )
        return cls(
            account_email=data.get("account_email"),
            history_id=data.get("history_id"),
            last_sync_mailbox=data.get("last_sync_mailbox"),
            messages=messages,
            classifications=classifications,
            corrections=corrections,
            followups=followups,
            read_later=read_later,
            digest_audit_events=digest_audit_events,
            label_audit_events=label_audit_events,
            automation_policy=automation_policy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_email": self.account_email,
            "history_id": self.history_id,
            "last_sync_mailbox": self.last_sync_mailbox,
            "messages": {
                message_id: message.to_dict()
                for message_id, message in sorted(self.messages.items())
            },
            "classifications": {
                message_id: classification.to_dict()
                for message_id, classification in sorted(self.classifications.items())
            },
            "corrections": {
                message_id: correction.to_dict()
                for message_id, correction in sorted(self.corrections.items())
            },
            "followups": {
                message_id: marker.to_dict()
                for message_id, marker in sorted(self.followups.items())
            },
            "read_later": {
                message_id: marker.to_dict()
                for message_id, marker in sorted(self.read_later.items())
            },
            "digest_audit_events": [
                event.to_dict() for event in self.digest_audit_events
            ],
            "label_audit_events": [
                event.to_dict() for event in self.label_audit_events
            ],
            "automation_policy": self.automation_policy.to_dict(),
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
    path.chmod(0o600)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    content = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    temp_path.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(temp_path, flags, 0o600), "wb") as temp_file:
        temp_file.write(content)
    temp_path.replace(path)
