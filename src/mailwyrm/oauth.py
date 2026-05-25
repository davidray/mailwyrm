from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from mailwyrm.models import GMAIL_READONLY_SCOPE, GmailToken


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_PATH = "/oauth2callback"


class OAuthError(RuntimeError):
    pass


def load_installed_client(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    installed = data.get("installed") or data.get("web")
    if not installed:
        raise OAuthError("client secret JSON must contain an 'installed' or 'web' client")

    return {
        "client_id": str(installed["client_id"]),
        "client_secret": str(installed["client_secret"]),
    }


def authorize(client_secret_path: Path, *, port: int = 8765) -> GmailToken:
    client = load_installed_client(client_secret_path)
    redirect_uri = f"http://127.0.0.1:{port}{REDIRECT_PATH}"
    code = _receive_authorization_code(client["client_id"], redirect_uri, port)
    token_response = _post_form(
        TOKEN_URL,
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    return _token_from_response(token_response)


def refresh_token(client_secret_path: Path, token: GmailToken) -> GmailToken:
    if not token.refresh_token:
        raise OAuthError("stored token does not include a refresh token; run auth again")

    client = load_installed_client(client_secret_path)
    token_response = _post_form(
        TOKEN_URL,
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
        },
    )
    refreshed = _token_from_response(token_response)
    return GmailToken(
        access_token=refreshed.access_token,
        expires_at=refreshed.expires_at,
        scope=refreshed.scope or token.scope,
        token_type=refreshed.token_type,
        refresh_token=token.refresh_token,
    )


def token_is_expired(token: GmailToken, *, skew_seconds: int = 60) -> bool:
    return token.expires_at <= time.time() + skew_seconds


def _receive_authorization_code(client_id: str, redirect_uri: str, port: int) -> str:
    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    url = f"{AUTH_URL}?{query}"
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if parsed.path != parsed_redirect.path:
                self.send_error(404)
                return
            if "error" in params:
                result["error"] = params["error"][0]
                self._send_text("Mailwyrm authorization failed. You can close this tab.")
                return
            if "code" not in params:
                result["error"] = "authorization response did not include a code"
                self._send_text("Mailwyrm authorization failed. You can close this tab.")
                return

            result["code"] = params["code"][0]
            self._send_text("Mailwyrm authorization complete. You can close this tab.")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_text(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    with HTTPServer(("127.0.0.1", port), CallbackHandler) as server:
        print(f"Opening Gmail authorization in your browser: {url}")
        webbrowser.open(url)
        server.handle_request()

    if result.get("error"):
        raise OAuthError(result["error"])
    if not result.get("code"):
        raise OAuthError("authorization did not complete")
    return result["code"]


def _post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _token_from_response(data: dict[str, Any]) -> GmailToken:
    if "access_token" not in data:
        raise OAuthError(f"token response did not include an access token: {data}")
    expires_in = int(data.get("expires_in", 3600))
    return GmailToken(
        access_token=str(data["access_token"]),
        refresh_token=data.get("refresh_token"),
        expires_at=time.time() + expires_in,
        scope=str(data.get("scope", "")),
        token_type=str(data.get("token_type", "Bearer")),
    )


def add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file.",
    )
    parser.add_argument(
        "--port",
        default=8765,
        type=int,
        help="Local callback port for the OAuth browser flow.",
    )

