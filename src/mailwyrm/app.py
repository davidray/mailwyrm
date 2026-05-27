from __future__ import annotations

import json
import mimetypes
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse

from mailwyrm.actions import (
    ACTION_TRASH_AFTER_DIGEST,
    ActionPlan,
    build_action_plans,
    build_trash_preview,
    complete_conversation,
    message_matches_mailbox,
    trash_digest_bundle,
)
from mailwyrm.actions import render_action_preview, render_trash_preview
from mailwyrm.classifier import classify_message
from mailwyrm.cockpit import (
    SUPPORTED_MAILBOXES,
    build_daily_cockpit_payload,
    build_message_detail_payload,
)
from mailwyrm.config import state_path, token_path
from mailwyrm.corrections import (
    CorrectionError,
    add_review_resolution,
    effective_classification,
)
from mailwyrm.daily import render_daily_preview
from mailwyrm.digest import build_digest_bundles, mark_digest_items
from mailwyrm.followups import set_followup
from mailwyrm.gmail import GmailApiError, GmailClient
from mailwyrm.labels import build_label_plans, render_label_preview
from mailwyrm.models import GMAIL_MODIFY_SCOPE
from mailwyrm.oauth import OAuthError, refresh_token, token_is_expired
from mailwyrm.store import MailwyrmState, read_state, read_token, write_state, write_token
from mailwyrm.sync import render_sync_summary, sync_mailbox_from_gmail


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
    client_secret: Path | None = None,
    show_metrics: bool = False,
) -> None:
    server = create_app_server(
        host=host,
        port=port,
        mailbox=mailbox,
        limit=limit,
        audit_limit=audit_limit,
        client_secret=client_secret,
        show_metrics=show_metrics,
    )
    print(f"Mailwyrm app listening at http://{host}:{port}")
    print("Local app view. Explicit browser actions may update Gmail when configured.")
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
    client_secret: Path | None = None,
    show_metrics: bool = False,
) -> ThreadingHTTPServer:
    if mailbox not in SUPPORTED_MAILBOXES:
        raise ValueError(_mailbox_error())
    handler = _handler(
        mailbox=mailbox,
        limit=limit,
        audit_limit=audit_limit,
        client_secret=client_secret,
        show_metrics=show_metrics,
    )
    return ThreadingHTTPServer((host, port), handler)


def _handler(
    *,
    mailbox: str,
    limit: int,
    audit_limit: int,
    client_secret: Path | None,
    show_metrics: bool,
):
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
            if parsed_url.path == "/api/gmail-sync":
                self._send_gmail_sync(parsed_url.query)
                return
            if parsed_url.path == "/api/review-resolution":
                self._send_review_resolution()
                return
            if parsed_url.path == "/api/machine-bundle/got-it":
                self._send_machine_bundle_got_it()
                return
            if parsed_url.path == "/api/followup":
                self._send_followup()
                return
            if parsed_url.path == "/api/conversation-complete":
                self._send_conversation_complete()
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
                    client_secret=client_secret,
                )
                payload["features"] = {
                    **payload.get("features", {}),
                    "show_metrics": show_metrics,
                }
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

        def _send_gmail_sync(self, query: str) -> None:
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
            try:
                client = _gmail_read_client(client_secret)
                payload = sync_gmail_messages(
                    client,
                    state,
                    limit=request_limit,
                    mailbox=request_mailbox,
                )
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except GmailApiError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_GATEWAY)
                return
            except OAuthError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as error:
                self._send_json(
                    {"error": f"unexpected Gmail sync error: {error}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            write_state(state_file, state)
            self._send_json(payload)

        def _send_review_resolution(self) -> None:
            if not _is_app_mutation_request(self.headers):
                self._send_json(
                    {"error": "local mutation requests must come from the Mailwyrm app"},
                    status=HTTPStatus.FORBIDDEN,
                )
                return

            try:
                request = self._read_json_request()
                message_id = _request_string(request, "message_id")
                resolution = _request_string(request, "resolution")
                machine_type = _optional_request_string(request, "machine_type")
                reason = _optional_request_string(request, "reason") or ""
                request_mailbox = _request_mailbox(request, mailbox)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            state_file = state_path()
            state = read_state(state_file)
            try:
                correction = add_review_resolution(
                    state,
                    message_id=message_id,
                    resolution=resolution,
                    machine_type=machine_type,
                    reason=reason,
                )
                detail = build_message_detail_payload(
                    state,
                    message_id=message_id,
                    mailbox=request_mailbox,
                )
            except CorrectionError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except KeyError:
                self._send_json(
                    {"error": "message is not in the local index"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return

            write_state(state_file, state)
            self._send_json(
                {
                    "title": "Review Resolution",
                    "mutated_local_state": True,
                    "mutates_gmail": False,
                    "message": "Saved local review resolution.",
                    "correction": correction.to_dict(),
                    "detail": detail,
                }
            )

        def _send_machine_bundle_got_it(self) -> None:
            if not _is_app_mutation_request(self.headers):
                self._send_json(
                    {"error": "local mutation requests must come from the Mailwyrm app"},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            if client_secret is None:
                self._send_json(
                    {"error": "client secret is required before Gmail can be mutated"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                request = self._read_json_request()
                machine_type = _request_string(request, "machine_type")
                request_mailbox = _request_mailbox(request, mailbox)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            state_file = state_path()
            state = read_state(state_file)
            bundles = {
                bundle.machine_type: bundle for bundle in build_digest_bundles(state)
            }
            bundle = bundles.get(machine_type)
            if bundle is None:
                self._send_json(
                    {"error": "machine bundle is not available"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return

            plans = _bundle_trash_plans(state, machine_type, mailbox=request_mailbox)
            if not plans:
                self._send_json(
                    {"error": "no bundle messages are available in this mailbox"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                client = _gmail_modify_client(client_secret)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            mark_digest_items(state)
            result = trash_digest_bundle(client, state, plans)
            write_state(state_file, state)
            self._send_json(
                {
                    "title": "Machine Bundle Cleared",
                    "machine_type": machine_type,
                    "mutated_local_state": True,
                    "mutates_gmail": result.applied > 0,
                    "message": (
                        f"Moved {result.applied} {bundle.title.lower()} "
                        "message(s) to Gmail Trash. "
                        f"Kept {result.skipped_followup} follow-up message(s)."
                    ),
                    "applied": result.applied,
                    "skipped_already_trashed": result.skipped_already_trashed,
                    "skipped_followup": result.skipped_followup,
                    "gmail_refresh_hint": (
                        "Gmail may need a browser refresh before the changes are visible."
                    ),
                }
            )

        def _send_followup(self) -> None:
            if not _is_app_mutation_request(self.headers):
                self._send_json(
                    {"error": "local mutation requests must come from the Mailwyrm app"},
                    status=HTTPStatus.FORBIDDEN,
                )
                return

            try:
                request = self._read_json_request()
                message_ids = _request_string_list(request, "message_ids")
                followup = _request_bool(request, "followup")
                reason = _optional_request_string(request, "reason") or ""
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            state_file = state_path()
            state = read_state(state_file)
            try:
                result = set_followup(
                    state,
                    message_ids=message_ids,
                    followup=followup,
                    reason=reason,
                )
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            write_state(state_file, state)
            self._send_json(
                {
                    "title": "Follow-up Updated",
                    "mutated_local_state": result["changed"] > 0,
                    "mutates_gmail": False,
                    "message": (
                        "Marked message(s) for follow-up."
                        if followup
                        else "Removed follow-up marker."
                    ),
                    **result,
                }
            )

        def _send_conversation_complete(self) -> None:
            if not _is_app_mutation_request(self.headers):
                self._send_json(
                    {"error": "local mutation requests must come from the Mailwyrm app"},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            if client_secret is None:
                self._send_json(
                    {"error": "client secret is required before Gmail can be mutated"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                request = self._read_json_request()
                thread_id = _request_string(request, "thread_id")
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            state_file = state_path()
            state = read_state(state_file)
            try:
                client = _gmail_modify_client(client_secret)
                result = complete_conversation(client, state, thread_id=thread_id)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            write_state(state_file, state)
            self._send_json(
                {
                    "title": "Conversation Complete",
                    "thread_id": thread_id,
                    "mutated_local_state": result.applied > 0,
                    "mutates_gmail": result.applied > 0,
                    "message": (
                        f"Archived {result.applied} inbox message(s) "
                        "from this conversation."
                    ),
                    "applied": result.applied,
                    "skipped_not_in_inbox": result.skipped_not_in_inbox,
                    "gmail_refresh_hint": (
                        "Gmail may need a browser refresh before the changes are visible."
                    ),
                }
            )

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

        def _read_json_request(self) -> dict:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Content-Length must be an integer") from error
            if content_length <= 0:
                raise ValueError("request body is required")
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError("request body must be valid JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

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


def _request_string(request: dict, name: str) -> str:
    value = _optional_request_string(request, name)
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _request_string_list(request: dict, name: str) -> list[str]:
    value = request.get(name)
    if not isinstance(value, list):
        raise ValueError(f"{name} is required")
    values = [str(item).strip() for item in value]
    values = [item for item in values if item]
    if not values:
        raise ValueError(f"{name} is required")
    return values


def _request_bool(request: dict, name: str) -> bool:
    value = request.get(name)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be true or false")


def _optional_request_string(request: dict, name: str) -> str | None:
    value = request.get(name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _request_mailbox(request: dict, default: str) -> str:
    value = _optional_request_string(request, "mailbox") or default
    if value not in SUPPORTED_MAILBOXES:
        raise ValueError(_mailbox_error())
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
        classification = state.classifications.get(message.id)
        if classification is None or _needs_review_type_refresh(classification):
            state.classifications[message.id] = classify_message(message)
            classified += 1
        else:
            skipped_already_classified += 1
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


def sync_gmail_messages(
    client,
    state: MailwyrmState,
    *,
    limit: int,
    mailbox: str,
) -> dict[str, object]:
    stats = sync_mailbox_from_gmail(
        client,
        state,
        limit=limit,
        mailbox=mailbox,
        include_body=True,
    )
    return {
        "title": "Gmail Sync",
        "mailbox": mailbox,
        "limit": limit,
        "mutated_local_state": True,
        "mutates_gmail": False,
        "matched_messages": stats.fetched,
        "message": render_sync_summary(
            stats,
            mailbox,
            state.account_email,
        ),
        "report_lines": [
            f"Fetched: {stats.fetched}",
            f"New: {stats.new}",
            f"Updated: {stats.updated}",
            f"Unchanged: {stats.unchanged}",
            f"Label changes: {stats.label_changes}",
            "Stored bounded body text for classification and summaries.",
            "Gmail was not modified.",
        ],
    }


def _needs_review_type_refresh(classification) -> bool:
    return classification.category == "needs_review" and classification.review_type is None


def _bundle_trash_plans(
    state: MailwyrmState,
    machine_type: str,
    *,
    mailbox: str,
) -> list[ActionPlan]:
    plans: list[ActionPlan] = []
    for message in sorted(
        state.messages.values(),
        key=lambda record: record.internal_date or "",
        reverse=True,
    ):
        if not message_matches_mailbox(message, mailbox):
            continue
        classification = state.classifications.get(message.id)
        if classification is None:
            continue
        classification = effective_classification(
            classification,
            state.corrections.get(message.id),
        )
        if classification.category != "machine":
            continue
        if (classification.machine_type or "transactional") != machine_type:
            continue
        plans.append(
            ActionPlan(
                message=message,
                classification=classification,
                action=ACTION_TRASH_AFTER_DIGEST,
                reason=f"User clicked Got it for {machine_type} bundle.",
            )
        )
    return plans


def _gmail_modify_client(client_secret: Path) -> GmailClient:
    token = read_token(token_path())
    if token is None:
        raise ValueError("No Gmail token found. Run `mailwyrm auth --scope modify` first.")
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        raise ValueError(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first."
        )
    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)
    return GmailClient(token)


def _gmail_read_client(client_secret: Path | None) -> GmailClient:
    token = read_token(token_path())
    if token is None:
        raise ValueError("No Gmail token found. Run `mailwyrm auth` first.")
    if token_is_expired(token):
        if client_secret is None:
            raise ValueError(
                "client secret is required to refresh the stored Gmail token"
            )
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)
    return GmailClient(token)
