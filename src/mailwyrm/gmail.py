from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from mailwyrm.models import DEFAULT_METADATA_HEADERS, GmailToken, MAILWYRM_LABEL_NAMES


GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


class GmailApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class GmailLabel:
    id: str
    name: str


class GmailClient:
    def __init__(self, token: GmailToken) -> None:
        self.token = token

    def profile(self) -> dict[str, Any]:
        return self._get("/users/me/profile")

    def list_messages(
        self,
        *,
        max_results: int = 25,
        label_ids: tuple[str, ...] | None = ("INBOX",),
        include_spam_trash: bool = False,
    ) -> list[dict[str, Any]]:
        query: dict[str, str | int] = {"maxResults": max_results}
        if include_spam_trash:
            query["includeSpamTrash"] = "true"
        url = f"{GMAIL_API_BASE}/users/me/messages?{urllib.parse.urlencode(query)}"
        if label_ids:
            label_query = "&".join(
                f"labelIds={urllib.parse.quote(label)}" for label in label_ids
            )
            url = f"{url}&{label_query}"
        data = self._request(url)
        return list(data.get("messages", []))

    def get_message_metadata(
        self,
        message_id: str,
        *,
        headers: tuple[str, ...] = DEFAULT_METADATA_HEADERS,
    ) -> dict[str, Any]:
        query = [
            ("format", "metadata"),
            *[("metadataHeaders", header) for header in headers],
        ]
        encoded = urllib.parse.urlencode(query)
        return self._get(f"/users/me/messages/{urllib.parse.quote(message_id)}?{encoded}")

    def list_labels(self) -> list[GmailLabel]:
        data = self._get("/users/me/labels")
        return [
            GmailLabel(id=str(label["id"]), name=str(label["name"]))
            for label in data.get("labels", [])
        ]

    def create_label(self, name: str) -> GmailLabel:
        data = self._post(
            "/users/me/labels",
            {
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        return GmailLabel(id=str(data["id"]), name=str(data["name"]))

    def ensure_mailwyrm_labels(
        self,
        label_names: tuple[str, ...] = MAILWYRM_LABEL_NAMES,
    ) -> dict[str, GmailLabel]:
        labels_by_name = {label.name: label for label in self.list_labels()}
        ensured: dict[str, GmailLabel] = {}
        for label_name in label_names:
            label = labels_by_name.get(label_name)
            if label is None:
                label = self.create_label(label_name)
                labels_by_name[label_name] = label
            ensured[label_name] = label
        return ensured

    def add_labels_to_message(self, message_id: str, label_ids: list[str]) -> None:
        self.modify_message_labels(
            message_id,
            add_label_ids=label_ids,
            remove_label_ids=[],
        )

    def remove_labels_from_message(self, message_id: str, label_ids: list[str]) -> None:
        self.modify_message_labels(
            message_id,
            add_label_ids=[],
            remove_label_ids=label_ids,
        )

    def modify_message_labels(
        self,
        message_id: str,
        *,
        add_label_ids: list[str],
        remove_label_ids: list[str],
    ) -> None:
        self._post(
            f"/users/me/messages/{urllib.parse.quote(message_id, safe='')}/modify",
            {
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids,
            },
        )

    def trash_message(self, message_id: str) -> None:
        self._post(
            f"/users/me/messages/{urllib.parse.quote(message_id, safe='')}/trash",
            {},
        )

    def _get(self, path: str) -> dict[str, Any]:
        return self._request(f"{GMAIL_API_BASE}{path}")

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(body).encode("utf-8")
        return self._request(
            f"{GMAIL_API_BASE}{path}",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        method: str | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Authorization": f"Bearer {self.token.access_token}"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GmailApiError(f"Gmail API error {error.code}: {detail}") from error
