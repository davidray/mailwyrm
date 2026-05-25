from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from mailwyrm.models import DEFAULT_METADATA_HEADERS, GmailToken


GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


class GmailApiError(RuntimeError):
    pass


class GmailClient:
    def __init__(self, token: GmailToken) -> None:
        self.token = token

    def profile(self) -> dict[str, Any]:
        return self._get("/users/me/profile")

    def list_messages(
        self,
        *,
        max_results: int = 25,
        label_ids: tuple[str, ...] = ("INBOX",),
    ) -> list[dict[str, Any]]:
        query: dict[str, str | int] = {"maxResults": max_results}
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

    def _get(self, path: str) -> dict[str, Any]:
        return self._request(f"{GMAIL_API_BASE}{path}")

    def _request(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.token.access_token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GmailApiError(f"Gmail API error {error.code}: {detail}") from error

