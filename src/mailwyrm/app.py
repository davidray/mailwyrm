from __future__ import annotations

import json
import mimetypes
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse

from mailwyrm.actions import build_action_plans, build_trash_preview, message_matches_mailbox
from mailwyrm.actions import render_action_preview, render_trash_preview
from mailwyrm.classifier import classify_message
from mailwyrm.cockpit import (
    SUPPORTED_MAILBOXES,
    build_daily_cockpit_payload,
    build_message_detail_payload,
)
from mailwyrm.config import state_path
from mailwyrm.daily import render_daily_preview
from mailwyrm.labels import build_label_plans, render_label_preview
from mailwyrm.store import MailwyrmState, read_state, write_state


DEFAULT_APP_HOST = "127.0.0.1"
DEFAULT_APP_PORT = 8766
SUPPORTED_PREVIEW_WORKFLOWS = ("daily-preview", "labels", "archive", "trash")
APP_MUTATION_HEADER = "X-Mailwyrm-App"
APP_MUTATION_HEADER_VALUE = "local-ui"


def run_app_server(
    *,
    host: str = DEFAULT_APP_HOST,
    port: int = DEFAULT_APP_PORT,
    mailbox: str = "inbox",
    limit: int = 25,
    audit_limit: int = 10,
) -> None:
    server = create_app_server(
        host=host,
        port=port,
        mailbox=mailbox,
        limit=limit,
        audit_limit=audit_limit,
    )
    print(f"Mailwyrm app listening at http://{host}:{port}")
    print("Local app view. Browser actions may update local state; Gmail mutations require CLI.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Mailwyrm app.")
    finally:
        server.server_close()


def create_app_server(
    *,
    host: str = DEFAULT_APP_HOST,
    port: int = DEFAULT_APP_PORT,
    mailbox: str = "inbox",
    limit: int = 25,
    audit_limit: int = 10,
) -> ThreadingHTTPServer:
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError(_mailbox_error())
    handler = _handler(mailbox=mailbox, limit=limit, audit_limit=audit_limit)
    return ThreadingHTTPServer((host, port), handler)


def _handler(*, mailbox: str, limit: int, audit_limit: int):
    class MailwyrmAppHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed_url = urlparse(self.path)
            if parsed_url.path == "/api/daily-cockpit":
                self._send_cockpit_payload(parsed_url.query)
                return
            if parsed_url.path == "/api/workflow-preview":
                self._send_workflow_preview(parsed_url.query)
                return
            if parsed_url.path == "/api/message-detail":
                self._send_message_detail(parsed_url.query)
                return
            if parsed_url.path == "/healthz":
                self._send_json({"ok": True})
                return
            self._send_static(parsed_url.path)

        def do_POST(self) -> None:
            parsed_url = urlparse(self.path)
            if parsed_url.path == "/api/local-classify":
                self._send_local_classify(parsed_url.query)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args) -> None:
            return

        def _send_cockpit_payload(self, query: str) -> None:
            params = parse_qs(query)
            try:
                request_limit = _query_int(params, "limit", limit)
                request_audit_limit = _query_int(params, "audit_limit", audit_limit)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                request_mailbox = _query_mailbox(params, mailbox)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                payload = build_daily_cockpit_payload(
                    read_state(state_path()),
                    limit=request_limit,
                    mailbox=request_mailbox,
                    audit_limit=request_audit_limit,
                )
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(payload)

        def _send_local_classify(self, query: str) -> None:
            if not _is_app_mutation_request(self.headers):
                self._send_json(
                    {"error": "local mutation requests must come from the Mailwyrm app"},
                    status=HTTPStatus.FORBIDDEN,
                )
                return

            params = parse_qs(query)
            try:
                request_limit = _query_int(params, "limit", limit)
                request_mailbox = _query_mailbox(params, mailbox)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            state_file = state_path()
            state = read_state(state_file)
            payload = classify_local_messages(
                state,
                limit=request_limit,
                mailbox=request_mailbox,
            )
            write_state(state_file, state)
            self._send_json(payload)

        def _send_workflow_preview(self, query: str) -> None:
            params = parse_qs(query)
            try:
                request_limit = _query_int(params, "limit", limit)
                request_mailbox = _query_mailbox(params, mailbox)
                workflow = _query_workflow(params)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                payload = build_workflow_preview_payload(
                    read_state(state_path()),
                    workflow=workflow,
                    limit=request_limit,
                    mailbox=request_mailbox,
                )
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(payload)

        def _send_message_detail(self, query: str) -> None:
            params = parse_qs(query)
            try:
                request_mailbox = _query_mailbox(params, mailbox)
                message_id = _query_message_id(params)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                payload = build_message_detail_payload(
                    read_state(state_path()),
                    message_id=message_id,
                    mailbox=request_mailbox,
                )
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except KeyError:
                self._send_json(
                    {"error": "message is not in the local index"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self._send_json(payload)

        def _send_static(self, request_path: str) -> None:
            relative_path = "index.html" if request_path in {"", "/"} else request_path[1:]
            relative_path = PurePosixPath(relative_path)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            file_path = resources.files("mailwyrm").joinpath("static", *relative_path.parts)
            if not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_type = (
                mimetypes.guess_type(str(relative_path))[0]
                or "application/octet-stream"
            )
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _send_json(
            self,
            payload: dict,
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            content = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

    return MailwyrmAppHandler


def _query_int(params: dict[str, list[str]], name: str, default: int) -> int:
    raw_value = params.get(name, [str(default)])[0]
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _query_mailbox(params: dict[str, list[str]], default: str) -> str:
    value = params.get("mailbox", [default])[0]
    if value not in SUPPORTED_MAILBOXES:
        raise ValueError(_mailbox_error())
    return value


def _query_workflow(params: dict[str, list[str]]) -> str:
    value = params.get("workflow", [""])[0]
    if value not in SUPPORTED_PREVIEW_WORKFLOWS:
        raise ValueError("workflow must be one of daily-preview, labels, archive, or trash")
    return value


def _query_message_id(params: dict[str, list[str]]) -> str:
    value = params.get("message_id", [""])[0].strip()
    if not value:
        raise ValueError("message_id is required")
    return value


def _mailbox_error() -> str:
    return f"mailbox must be one of {', '.join(SUPPORTED_MAILBOXES)}"


def _is_app_mutation_request(headers) -> bool:
    return headers.get(APP_MUTATION_HEADER) == APP_MUTATION_HEADER_VALUE


def build_workflow_preview_payload(
    state: MailwyrmState,
    *,
    workflow: str,
    limit: int | None = 25,
    mailbox: str = "inbox",
) -> dict[str, object]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError(_mailbox_error())

    if workflow == "daily-preview":
        title = "Daily Workflow Preview"
        report = render_daily_preview(
            state,
            title_date=datetime.now(UTC).date().isoformat(),
            limit=limit,
            mailbox=mailbox,
        )
    elif workflow == "labels":
        title = "Gmail Label Preview"
        report = render_label_preview(
            build_label_plans(state, limit=limit, mailbox=mailbox)
        )
    elif workflow == "archive":
        title = "Mailbox Action Preview"
        report = render_action_preview(
            build_action_plans(state, limit=limit, mailbox=mailbox)
        )
    elif workflow == "trash":
        title = "Trash Policy Preview"
        report = render_trash_preview(
            build_trash_preview(state, limit=limit, mailbox=mailbox)
        )
    else:
        raise ValueError("workflow must be one of daily-preview, labels, archive, or trash")

    return {
        "title": title,
        "workflow": workflow,
        "mailbox": mailbox,
        "limit": limit,
        "read_only": True,
        "report": report,
    }


def classify_local_messages(
    state: MailwyrmState,
    *,
    limit: int | None = 25,
    mailbox: str = "inbox",
) -> dict[str, object]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError("mailbox must be one of inbox, all-mail, or trash")

    matched = 0
    classified = 0
    skipped_already_classified = 0
    if limit == 0:
        return {
            "title": "Local Classification",
            "mailbox": mailbox,
            "limit": limit,
            "mutated_local_state": False,
            "mutates_gmail": False,
            "matched_messages": matched,
            "classified_messages": classified,
            "skipped_already_classified": skipped_already_classified,
            "message": (
                f"Classified {classified} {mailbox} message(s) locally. "
                f"Skipped {skipped_already_classified} already-classified message(s)."
            ),
        }

    for message in sorted(
        state.messages.values(),
        key=lambda record: record.internal_date or "",
        reverse=True,
    ):
        if not message_matches_mailbox(message, mailbox):
            continue
        matched += 1
        if message.id in state.classifications:
            skipped_already_classified += 1
        else:
            state.classifications[message.id] = classify_message(message)
            classified += 1
        if limit is not None and matched >= limit:
            break

    return {
        "title": "Local Classification",
        "mailbox": mailbox,
        "limit": limit,
        "mutated_local_state": classified > 0,
        "mutates_gmail": False,
        "matched_messages": matched,
        "classified_messages": classified,
        "skipped_already_classified": skipped_already_classified,
        "message": (
            f"Classified {classified} {mailbox} message(s) locally. "
            f"Skipped {skipped_already_classified} already-classified message(s)."
        ),
    }
