from __future__ import annotations

import argparse
import copy
import sys
from datetime import UTC, datetime
from pathlib import Path

from mailwyrm import __version__
from mailwyrm.app import DEFAULT_APP_HOST, DEFAULT_APP_PORT, run_app_server
from mailwyrm.actions import (
    apply_archive_action_plans,
    apply_trash_action_preview,
    build_action_plans,
    build_trash_preview,
    render_action_audit,
    render_action_preview,
    render_trash_preview,
    restore_archived_message,
    restore_trashed_message,
)
from mailwyrm.classifier import classify_message
from mailwyrm.config import (
    client_secret_path,
    show_metrics_enabled,
    state_path,
    token_path,
)
from mailwyrm.corrections import CorrectionError, add_correction, correction_report
from mailwyrm.corrections import effective_classification
from mailwyrm.daily import render_daily_cockpit, render_daily_preview, render_daily_status
from mailwyrm.digest import mark_digest_items, render_digest
from mailwyrm.gmail import GmailApiError, GmailClient
from mailwyrm.labels import apply_label_plans, build_label_plans, render_label_preview
from mailwyrm.labels import (
    apply_digested_label_plans,
    build_digested_label_plans,
    render_digested_label_preview,
)
from mailwyrm.models import (
    CLASSIFICATION_CATEGORIES,
    GMAIL_MODIFY_SCOPE,
    MACHINE_TYPES,
    MessageRecord,
)
from mailwyrm.oauth import (
    add_auth_arguments,
    authorize,
    refresh_token,
    scope_for_name,
    token_is_expired,
)
from mailwyrm.policy import enable_trash_after_digest, render_policy_status
from mailwyrm.store import read_state, read_token, write_state, write_token
from mailwyrm.sync import render_sync_summary, sync_mailbox_from_gmail
from mailwyrm.sync import (
    HistoryReconcileStats,
    SYNC_MAILBOXES,
    merge_history_stats,
    reconcile_history,
    render_history_reconcile_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return auth_command(args.client_secret, args.port, args.scope)
    if args.command == "sync":
        return sync_command(
            args.client_secret,
            args.limit,
            args.mailbox,
            include_body=args.include_body,
            include_thread_context=args.include_thread_context,
            body_char_limit=args.body_char_limit,
            thread_context_limit=args.thread_context_limit,
        )
    if args.command == "sync-history":
        return sync_history_command(args.client_secret, args.max_pages)
    if args.command == "ensure-labels":
        return ensure_labels_command(args.client_secret)
    if args.command == "classify":
        return classify_command(args.limit, args.mailbox)
    if args.command == "digest":
        return digest_command(args)
    if args.command == "daily":
        return daily_command(args)
    if args.command == "correct":
        return correct_command(args)
    if args.command == "corrections":
        return corrections_command()
    if args.command == "policy":
        return policy_command(args)
    if args.command == "list":
        return list_command(args.limit, args.show_classification, args.mailbox)
    if args.command == "labels":
        return labels_command(args)
    if args.command == "actions":
        return actions_command(args)
    if args.command == "app":
        return app_command(
            args.host,
            args.port,
            args.mailbox,
            args.limit,
            args.audit_limit,
            args.client_secret,
            args.show_metrics,
        )

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailwyrm")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Authorize read-only Gmail access.")
    add_auth_arguments(auth_parser)

    sync_parser = subparsers.add_parser(
        "sync",
        help="Fetch recent Gmail message metadata into the local Mailwyrm index.",
    )
    sync_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    sync_parser.add_argument("--limit", default=25, type=int, help="Max messages to fetch.")
    sync_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to sync. Defaults to inbox.",
    )
    sync_parser.add_argument(
        "--include-body",
        action="store_true",
        help=(
            "Opt in to fetching bounded message body text for better "
            "classification and summaries."
        ),
    )
    sync_parser.add_argument(
        "--body-char-limit",
        default=4000,
        type=_non_negative_int,
        help="Max body characters to store per message when --include-body is set.",
    )
    sync_parser.add_argument(
        "--include-thread-context",
        action="store_true",
        help=(
            "When --include-body is set, fetch bounded full Gmail threads for "
            "selected messages so summaries can use nearby thread context."
        ),
    )
    sync_parser.add_argument(
        "--thread-context-limit",
        default=3,
        type=_positive_int,
        help="Maximum Gmail thread messages to store per selected thread. Defaults to 3.",
    )

    sync_history_parser = subparsers.add_parser(
        "sync-history",
        help="Reconcile local state from the stored Gmail history cursor.",
    )
    sync_history_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    sync_history_parser.add_argument(
        "--max-pages",
        default=10,
        type=_non_negative_int,
        help="Maximum Gmail history pages to reconcile. Defaults to 10.",
    )

    ensure_labels_parser = subparsers.add_parser(
        "ensure-labels",
        help="Create Gmail-visible Mailwyrm labels if they do not exist.",
    )
    ensure_labels_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )

    classify_parser = subparsers.add_parser(
        "classify",
        help="Classify locally indexed messages without mutating Gmail.",
    )
    classify_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max messages to classify. Defaults to all locally indexed messages.",
    )
    classify_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="all-mail",
        help="Mailbox scope to classify. Defaults to all-mail.",
    )

    digest_parser = subparsers.add_parser(
        "digest",
        help=(
            "Render a local machine-mail digest, or manage Gmail-visible "
            "digested labels."
        ),
    )
    digest_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the Markdown digest. Prints to stdout by default.",
    )
    digest_subparsers = digest_parser.add_subparsers(dest="digest_command")
    digest_labels_parser = digest_subparsers.add_parser(
        "labels",
        help="Preview or apply Gmail-visible labels for digested messages.",
    )
    digest_labels_subparsers = digest_labels_parser.add_subparsers(
        dest="digest_labels_command"
    )
    digest_labels_preview_parser = digest_labels_subparsers.add_parser(
        "preview",
        help="Preview Mailwyrm/Digested labels that would be applied.",
    )
    digest_labels_preview_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max digested label plans to preview. Defaults to all digested messages.",
    )
    digest_labels_apply_parser = digest_labels_subparsers.add_parser(
        "apply",
        help="Apply Mailwyrm/Digested labels to Gmail messages.",
    )
    digest_labels_apply_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    digest_labels_apply_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max digested label plans to apply. Defaults to all digested messages.",
    )

    daily_parser = subparsers.add_parser(
        "daily",
        help="Preview or apply the daily machine-mail workflow.",
    )
    daily_subparsers = daily_parser.add_subparsers(dest="daily_command")
    daily_cockpit_parser = daily_subparsers.add_parser(
        "cockpit",
        help="Render a read-only daily attention cockpit.",
    )
    daily_cockpit_parser.add_argument(
        "--limit",
        default=25,
        type=_non_negative_int,
        help="Max digest items and action plans to show. Defaults to 25.",
    )
    daily_cockpit_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope for mailbox actions. Defaults to inbox.",
    )
    daily_cockpit_parser.add_argument(
        "--audit-limit",
        default=10,
        type=_non_negative_int,
        help="Max recent audit events to show. Defaults to 10.",
    )
    daily_preview_parser = daily_subparsers.add_parser(
        "preview",
        help="Render digest, digested-label, and mailbox-action previews together.",
    )
    daily_preview_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max label and action plans to preview. Defaults to all eligible messages.",
    )
    daily_preview_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope for mailbox actions. Defaults to inbox.",
    )
    daily_apply_parser = daily_subparsers.add_parser(
        "apply",
        help=(
            "Render the daily report, mark digest items, apply digested labels, "
            "and archive eligible messages."
        ),
    )
    daily_apply_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    daily_apply_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max label and action plans to apply. Defaults to all eligible messages.",
    )
    daily_apply_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope for mailbox actions. Defaults to inbox.",
    )
    daily_status_parser = daily_subparsers.add_parser(
        "status",
        help="Summarize local digest, Gmail mutation, and mailbox action status.",
    )
    daily_status_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope for current mailbox action counts. Defaults to inbox.",
    )

    correct_parser = subparsers.add_parser(
        "correct",
        help="Store a local user correction for a message classification.",
    )
    correct_parser.add_argument("message_id", help="Gmail message ID from `mailwyrm list`.")
    correct_parser.add_argument(
        "category",
        choices=CLASSIFICATION_CATEGORIES,
        help="Corrected classification category.",
    )
    correct_parser.add_argument(
        "--machine-type",
        choices=MACHINE_TYPES,
        help="Optional machine subtype when category is machine.",
    )
    correct_parser.add_argument(
        "--reason",
        default="",
        help="Optional reason for the correction.",
    )

    subparsers.add_parser(
        "corrections",
        help="List local classification corrections.",
    )

    policy_parser = subparsers.add_parser(
        "policy",
        help="Show local automation policy.",
    )
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command")
    policy_subparsers.add_parser(
        "status",
        help="Show local automation policy without mutating Gmail or local state.",
    )
    policy_enable_trash_parser = policy_subparsers.add_parser(
        "enable-trash-after-digest",
        help="Enable local trash-after-digest policy without mutating Gmail.",
    )
    policy_enable_trash_parser.add_argument(
        "--confirm-trash-policy",
        action="store_true",
        help="Required confirmation that future trash commands may use this policy.",
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List messages stored in the local Mailwyrm index.",
    )
    list_parser.add_argument("--limit", default=25, type=int, help="Max messages to show.")
    list_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="all-mail",
        help="Mailbox scope to list from the local index. Defaults to all-mail.",
    )
    list_parser.add_argument(
        "--show-classification",
        action="store_true",
        help="Include local classification category and reason.",
    )

    labels_parser = subparsers.add_parser(
        "labels",
        help="Preview or apply Gmail-visible labels from local classifications.",
    )
    labels_subparsers = labels_parser.add_subparsers(dest="labels_command")
    labels_preview_parser = labels_subparsers.add_parser(
        "preview",
        help="Preview Gmail labels that would be applied.",
    )
    labels_preview_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max label plans to preview. Defaults to all classified messages.",
    )
    labels_preview_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to label. Defaults to inbox.",
    )
    labels_apply_parser = labels_subparsers.add_parser(
        "apply",
        help="Apply Gmail labels from local classifications.",
    )
    labels_apply_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    labels_apply_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max messages to label. Defaults to all classified messages.",
    )
    labels_apply_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to label. Defaults to inbox.",
    )

    actions_parser = subparsers.add_parser(
        "actions",
        help="Preview mailbox actions from local classifications.",
    )
    actions_subparsers = actions_parser.add_subparsers(dest="actions_command")
    actions_preview_parser = actions_subparsers.add_parser(
        "preview",
        help="Preview mailbox actions without mutating Gmail.",
    )
    actions_preview_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max action plans to preview. Defaults to all classified messages.",
    )
    actions_preview_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to preview. Defaults to inbox.",
    )
    actions_preview_trash_parser = actions_subparsers.add_parser(
        "preview-trash",
        help="Preview policy-gated trash_after_digest candidates without mutating Gmail.",
    )
    actions_preview_trash_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max eligible trash plans to preview. Defaults to all eligible messages.",
    )
    actions_preview_trash_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to preview. Defaults to inbox.",
    )
    actions_apply_archive_parser = actions_subparsers.add_parser(
        "apply-archive",
        help="Apply archive_after_digest plans by removing Gmail's INBOX label.",
    )
    actions_apply_archive_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    actions_apply_archive_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max action plans to consider. Defaults to all classified messages.",
    )
    actions_apply_archive_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to apply. Defaults to inbox.",
    )
    actions_apply_trash_parser = actions_subparsers.add_parser(
        "apply-trash",
        help="Apply policy-gated trash_after_digest plans using Gmail's trash operation.",
    )
    actions_apply_trash_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    actions_apply_trash_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Max eligible trash plans to apply. Defaults to all eligible messages.",
    )
    actions_apply_trash_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope to apply. Defaults to inbox.",
    )
    actions_audit_parser = actions_subparsers.add_parser(
        "audit",
        help="Show local Gmail mutation audit events.",
    )
    actions_audit_parser.add_argument(
        "--limit",
        default=25,
        type=int,
        help="Max audit events to show. Defaults to 25.",
    )
    actions_restore_archive_parser = actions_subparsers.add_parser(
        "restore-archive",
        help="Restore an archived message by adding Gmail's INBOX label.",
    )
    actions_restore_archive_parser.add_argument(
        "message_id",
        help="Gmail message ID to restore to the inbox.",
    )
    actions_restore_archive_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )
    actions_restore_trash_parser = actions_subparsers.add_parser(
        "restore-trash",
        help="Restore a trashed message by removing TRASH and adding INBOX.",
    )
    actions_restore_trash_parser.add_argument(
        "message_id",
        help="Gmail message ID to restore to the inbox.",
    )
    actions_restore_trash_parser.add_argument(
        "--client-secret",
        required=True,
        type=Path,
        help="Path to a Google OAuth client secret JSON file for token refresh.",
    )

    app_parser = subparsers.add_parser(
        "app",
        help="Run the read-only local Mailwyrm cockpit app.",
    )
    app_parser.add_argument(
        "--host",
        default=DEFAULT_APP_HOST,
        help=f"Host to bind. Defaults to {DEFAULT_APP_HOST}.",
    )
    app_parser.add_argument(
        "--port",
        default=DEFAULT_APP_PORT,
        type=_non_negative_int,
        help=f"Port to bind. Defaults to {DEFAULT_APP_PORT}.",
    )
    app_parser.add_argument(
        "--mailbox",
        choices=SYNC_MAILBOXES,
        default="inbox",
        help="Mailbox scope for mailbox actions. Defaults to inbox.",
    )
    app_parser.add_argument(
        "--limit",
        default=25,
        type=_non_negative_int,
        help="Max digest items and action plans to show. Defaults to 25.",
    )
    app_parser.add_argument(
        "--audit-limit",
        default=10,
        type=_non_negative_int,
        help="Max recent audit events to show. Defaults to 10.",
    )
    app_parser.add_argument(
        "--client-secret",
        default=None,
        type=Path,
        help=(
            "Optional OAuth client secret path to show in copyable Gmail CLI "
            "commands. Defaults to MAILWYRM_CLIENT_SECRET when set."
        ),
    )
    app_parser.add_argument(
        "--show-metrics",
        action="store_true",
        default=None,
        help=(
            "Show summary metric cards. Defaults to MAILWYRM_SHOW_METRICS, "
            "and is off when unset."
        ),
    )

    return parser


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def auth_command(client_secret: Path, port: int, scope_name: str) -> int:
    token = authorize(client_secret, port=port, scope=scope_for_name(scope_name))
    write_token(token_path(), token)
    print(f"Stored Gmail token at {token_path()}")
    return 0


def sync_command(
    client_secret: Path,
    limit: int,
    mailbox: str,
    *,
    include_body: bool = False,
    include_thread_context: bool = False,
    body_char_limit: int = 4000,
    thread_context_limit: int = 3,
) -> int:
    token = read_token(token_path())
    if token is None:
        print("No Gmail token found. Run `mailwyrm auth` first.", file=sys.stderr)
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    client = GmailClient(token)
    state = read_state(state_path())
    stats = sync_mailbox_from_gmail(
        client,
        state,
        limit=limit,
        mailbox=mailbox,
        include_body=include_body,
        include_thread_context=include_thread_context,
        body_char_limit=body_char_limit,
        thread_context_limit=thread_context_limit,
    )

    write_state(state_path(), state)
    print(render_sync_summary(stats, mailbox, state.account_email))
    if include_body:
        print(f"Stored up to {body_char_limit} body character(s) per message.")
    if include_thread_context:
        print(
            f"Stored up to {thread_context_limit} message(s) per selected thread "
            "for bounded context."
        )
    print(f"Local index: {state_path()}")
    return 0


def sync_history_command(client_secret: Path, max_pages: int) -> int:
    token = read_token(token_path())
    if token is None:
        print("No Gmail token found. Run `mailwyrm auth` first.", file=sys.stderr)
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    if not state.history_id:
        print(
            "No Gmail history cursor found. Run `mailwyrm sync` first.",
            file=sys.stderr,
        )
        return 1

    client = GmailClient(token)
    start_history_id = str(state.history_id)
    page_token = None
    pages = 0
    stats = HistoryReconcileStats()
    while pages < max_pages:
        try:
            response = client.list_history(
                start_history_id=start_history_id,
                page_token=page_token,
            )
            stats = merge_history_stats(
                stats,
                reconcile_history(
                    state,
                    response,
                    client=client,
                    include_body=True,
                ),
            )
        except GmailApiError as error:
            if error.status_code != 404:
                raise
            mailbox = state.last_sync_mailbox or "inbox"
            sync_stats = sync_mailbox_from_gmail(
                client,
                state,
                limit=None,
                mailbox=mailbox,
                include_body=True,
            )
            classified = _classify_unclassified_messages(state, mailbox=mailbox)
            write_state(state_path(), state)
            print(
                "Stored Gmail history cursor was too old for incremental "
                f"reconciliation. Ran a full {mailbox} sync instead."
            )
            print(render_sync_summary(sync_stats, mailbox, state.account_email))
            print(f"Classified {classified} newly synced message(s) locally.")
            print(f"Local index: {state_path()}")
            return 0
        pages += 1
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    classified = _classify_unclassified_messages(
        state,
        message_ids=stats.fetched_message_ids,
    )
    write_state(state_path(), state)
    print(render_history_reconcile_summary(stats, state.account_email))
    print(f"Classified {classified} newly fetched message(s) locally.")
    if page_token:
        print(
            "More Gmail history pages are available; rerun with a larger --max-pages.",
            file=sys.stderr,
        )
    print(f"Local index: {state_path()}")
    return 0


def ensure_labels_command(client_secret: Path) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    client = GmailClient(token)
    labels = client.ensure_mailwyrm_labels()
    for label_name, label in labels.items():
        print(f"{label_name}\t{label.id}")
    return 0


def classify_command(limit: int | None, mailbox: str = "all-mail") -> int:
    state = read_state(state_path())
    messages = sorted(
        (
            message
            for message in state.messages.values()
            if message_matches_mailbox(message, mailbox)
        ),
        key=lambda message: message.internal_date or "",
        reverse=True,
    )
    if not messages:
        print(
            f"No local {mailbox} messages. Run `mailwyrm sync` first.",
            file=sys.stderr,
        )
        return 1

    selected_messages = messages[:limit] if limit is not None else messages
    for message in selected_messages:
        classification = classify_message(message)
        state.classifications[message.id] = classification

    write_state(state_path(), state)
    print(f"Classified {len(selected_messages)} {mailbox} message(s) locally.")
    return 0


def _classify_unclassified_messages(
    state: MailwyrmState,
    *,
    message_ids: frozenset[str] | set[str] | None = None,
    mailbox: str | None = None,
) -> int:
    if message_ids is None:
        messages = list(state.messages.values())
    else:
        messages = [
            state.messages[message_id]
            for message_id in sorted(message_ids)
            if message_id in state.messages
        ]

    classified = 0
    for message in messages:
        if mailbox is not None and not message_matches_mailbox(message, mailbox):
            continue
        if message.id in state.classifications:
            continue
        state.classifications[message.id] = classify_message(message)
        classified += 1
    return classified


def digest_command(args: argparse.Namespace) -> int:
    if args.digest_command == "labels":
        return digest_labels_command(args)

    state = read_state(state_path())
    if not state.messages:
        print("No local messages. Run `mailwyrm sync` first.", file=sys.stderr)
        return 1
    if not state.classifications:
        print("No local classifications. Run `mailwyrm classify` first.", file=sys.stderr)
        return 1

    title_date = datetime.now(UTC).date().isoformat()
    digest = render_digest(state, title_date=title_date)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{digest}\n", encoding="utf-8")
        print(f"Wrote digest to {args.output}")
    else:
        print(digest)
    marked = mark_digest_items(state, title_date=title_date)
    write_state(state_path(), state)
    print(f"Marked {marked} message(s) as digested.")
    return 0


def digest_labels_command(args: argparse.Namespace) -> int:
    if args.digest_labels_command == "preview":
        state = read_state(state_path())
        plans = build_digested_label_plans(state, limit=args.limit)
        print(render_digested_label_preview(plans))
        return 0
    if args.digest_labels_command == "apply":
        return digest_labels_apply_command(args.client_secret, args.limit)

    print("Choose `preview` or `apply`.", file=sys.stderr)
    return 1


def digest_labels_apply_command(client_secret: Path, limit: int | None) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    plans = build_digested_label_plans(state, limit=limit)
    if not plans:
        print("No digested messages are ready for Gmail labels.")
        return 0

    print(render_digested_label_preview(plans))
    client = GmailClient(token)
    applied = apply_digested_label_plans(client, state, plans)
    write_state(state_path(), state)
    print(f"Applied Mailwyrm/Digested label to {applied} message(s).")
    return 0


def daily_command(args: argparse.Namespace) -> int:
    if args.daily_command == "cockpit":
        return daily_cockpit_command(args.limit, args.mailbox, args.audit_limit)
    if args.daily_command == "preview":
        return daily_preview_command(args.limit, args.mailbox)
    if args.daily_command == "apply":
        return daily_apply_command(args.client_secret, args.limit, args.mailbox)
    if args.daily_command == "status":
        return daily_status_command(args.mailbox)

    print("Choose `cockpit`, `preview`, `apply`, or `status`.", file=sys.stderr)
    return 1


def daily_cockpit_command(limit: int | None, mailbox: str, audit_limit: int) -> int:
    state = read_state(state_path())
    title_date = datetime.now(UTC).date().isoformat()
    print(
        render_daily_cockpit(
            state,
            title_date=title_date,
            limit=limit,
            mailbox=mailbox,
            audit_limit=audit_limit,
        )
    )
    return 0


def app_command(
    host: str,
    port: int,
    mailbox: str,
    limit: int,
    audit_limit: int,
    client_secret: Path | None = None,
    show_metrics: bool | None = None,
) -> int:
    client_secret = client_secret or client_secret_path()
    run_app_server(
        host=host,
        port=port,
        mailbox=mailbox,
        limit=limit,
        audit_limit=audit_limit,
        client_secret=client_secret,
        show_metrics=show_metrics_enabled() if show_metrics is None else show_metrics,
    )
    return 0


def daily_preview_command(limit: int | None, mailbox: str) -> int:
    state = read_state(state_path())
    if not state.messages:
        print("No local messages. Run `mailwyrm sync` first.", file=sys.stderr)
        return 1
    if not state.classifications:
        print("No local classifications. Run `mailwyrm classify` first.", file=sys.stderr)
        return 1

    title_date = datetime.now(UTC).date().isoformat()
    print(
        render_daily_preview(
            state,
            title_date=title_date,
            limit=limit,
            mailbox=mailbox,
        )
    )
    return 0


def daily_apply_command(client_secret: Path, limit: int | None, mailbox: str) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    if not state.messages:
        print("No local messages. Run `mailwyrm sync` first.", file=sys.stderr)
        return 1
    if not state.classifications:
        print("No local classifications. Run `mailwyrm classify` first.", file=sys.stderr)
        return 1

    title_date = datetime.now(UTC).date().isoformat()
    preview_state = copy.deepcopy(state)
    mark_digest_items(preview_state, title_date=title_date)
    print(
        render_daily_preview(
            preview_state,
            title_date=title_date,
            limit=limit,
            mailbox=mailbox,
            mutates_gmail=True,
        )
    )

    marked = mark_digest_items(state, title_date=title_date)
    digested_label_plans = build_digested_label_plans(state, limit=limit)
    action_plans = build_action_plans(state, limit=limit, mailbox=mailbox)

    client = GmailClient(token)
    labels_applied = apply_digested_label_plans(client, state, digested_label_plans)
    write_state(state_path(), state)
    archive_result = apply_archive_action_plans(client, state, action_plans)
    write_state(state_path(), state)

    print(f"Marked {marked} message(s) as digested.")
    print(f"Applied Mailwyrm/Digested label to {labels_applied} message(s).")
    print(
        f"Archived {archive_result.applied} message(s) by removing Gmail's INBOX label."
    )
    if archive_result.skipped_not_digested:
        print(
            f"Skipped {archive_result.skipped_not_digested} archive candidate(s) "
            "because they have not appeared in a digest yet."
        )
    if archive_result.skipped_followup:
        print(
            f"Skipped {archive_result.skipped_followup} archive candidate(s) "
            "because they are marked for follow-up."
        )
    print("Trash actions were not applied.")
    return 0


def daily_status_command(mailbox: str) -> int:
    state = read_state(state_path())
    print(render_daily_status(state, mailbox=mailbox))
    return 0


def correct_command(args: argparse.Namespace) -> int:
    state = read_state(state_path())
    try:
        correction = add_correction(
            state,
            message_id=args.message_id,
            category=args.category,
            machine_type=args.machine_type,
            reason=args.reason,
        )
    except CorrectionError as error:
        print(str(error), file=sys.stderr)
        return 1

    write_state(state_path(), state)
    print(f"Corrected {correction.message_id} to {correction.category}.")
    return 0


def corrections_command() -> int:
    state = read_state(state_path())
    print(correction_report(state))
    return 0


def policy_command(args: argparse.Namespace) -> int:
    if args.policy_command == "status":
        state = read_state(state_path())
        print(render_policy_status(state.automation_policy))
        return 0
    if args.policy_command == "enable-trash-after-digest":
        return policy_enable_trash_after_digest_command(args.confirm_trash_policy)

    print("Choose `status` or `enable-trash-after-digest`.", file=sys.stderr)
    return 1


def policy_enable_trash_after_digest_command(confirm_trash_policy: bool) -> int:
    if not confirm_trash_policy:
        print(
            "Refusing to enable trash-after-digest policy without "
            "`--confirm-trash-policy`.",
            file=sys.stderr,
        )
        return 1

    state = read_state(state_path())
    state.automation_policy = enable_trash_after_digest(state.automation_policy)
    write_state(state_path(), state)
    print(render_policy_status(state.automation_policy))
    return 0


def labels_command(args: argparse.Namespace) -> int:
    if args.labels_command == "preview":
        state = read_state(state_path())
        plans = build_label_plans(state, limit=args.limit, mailbox=args.mailbox)
        print(render_label_preview(plans))
        return 0
    if args.labels_command == "apply":
        return labels_apply_command(args.client_secret, args.limit, args.mailbox)

    print("Choose `preview` or `apply`.", file=sys.stderr)
    return 1


def labels_apply_command(client_secret: Path, limit: int | None, mailbox: str) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    plans = build_label_plans(state, limit=limit, mailbox=mailbox)
    if not plans:
        print("No classified messages are ready for Gmail labels.")
        return 0

    print(render_label_preview(plans))
    client = GmailClient(token)
    applied = apply_label_plans(client, state, plans)
    write_state(state_path(), state)
    print(f"Applied Gmail labels to {applied} message(s).")
    return 0


def actions_command(args: argparse.Namespace) -> int:
    if args.actions_command == "preview":
        state = read_state(state_path())
        plans = build_action_plans(state, limit=args.limit, mailbox=args.mailbox)
        print(render_action_preview(plans))
        return 0
    if args.actions_command == "preview-trash":
        state = read_state(state_path())
        preview = build_trash_preview(state, limit=args.limit, mailbox=args.mailbox)
        print(render_trash_preview(preview))
        return 0
    if args.actions_command == "apply-archive":
        return actions_apply_archive_command(
            args.client_secret,
            args.limit,
            args.mailbox,
        )
    if args.actions_command == "apply-trash":
        return actions_apply_trash_command(
            args.client_secret,
            args.limit,
            args.mailbox,
        )
    if args.actions_command == "audit":
        state = read_state(state_path())
        print(render_action_audit(state, limit=args.limit))
        return 0
    if args.actions_command == "restore-archive":
        return actions_restore_archive_command(args.client_secret, args.message_id)
    if args.actions_command == "restore-trash":
        return actions_restore_trash_command(args.client_secret, args.message_id)

    print(
        "Choose `preview`, `preview-trash`, `apply-archive`, "
        "`apply-trash`, `audit`, `restore-archive`, or `restore-trash`.",
        file=sys.stderr,
    )
    return 1


def actions_apply_archive_command(
    client_secret: Path,
    limit: int | None,
    mailbox: str,
) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    plans = build_action_plans(state, limit=limit, mailbox=mailbox)
    if not plans:
        print("No classified messages are ready for mailbox actions.")
        return 0

    print(render_action_preview(plans, mutates_gmail=True))
    client = GmailClient(token)
    result = apply_archive_action_plans(client, state, plans)
    write_state(state_path(), state)
    print(f"Archived {result.applied} message(s) by removing Gmail's INBOX label.")
    if result.skipped_not_digested:
        print(
            f"Skipped {result.skipped_not_digested} archive candidate(s) "
            "because they have not appeared in a digest yet."
        )
    if result.skipped_followup:
        print(
            f"Skipped {result.skipped_followup} archive candidate(s) "
            "because they are marked for follow-up."
        )
    return 0


def actions_apply_trash_command(
    client_secret: Path,
    limit: int | None,
    mailbox: str,
) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    preview = build_trash_preview(state, limit=limit, mailbox=mailbox)
    print(render_trash_preview(preview, mutates_gmail=bool(preview.plans)))
    if not preview.plans:
        if not preview.policy_enabled:
            print("Trash policy is disabled; no Gmail trash actions were applied.")
        else:
            print("No messages are eligible for Gmail trash.")
        return 0

    client = GmailClient(token)
    result = apply_trash_action_preview(client, state, preview)
    write_state(state_path(), state)
    print(f"Trashed {result.applied} message(s) using Gmail's trash operation.")
    if result.skipped_policy_disabled:
        print(
            f"Skipped {result.skipped_policy_disabled} trash candidate(s) "
            "because trash policy is disabled."
        )
    if result.skipped_not_digested:
        print(
            f"Skipped {result.skipped_not_digested} trash candidate(s) "
            "because they have not appeared in a digest yet."
        )
    if result.skipped_already_trashed:
        print(
            f"Skipped {result.skipped_already_trashed} trash candidate(s) "
            "because they are already in Gmail Trash."
        )
    if result.skipped_followup:
        print(
            f"Skipped {result.skipped_followup} trash candidate(s) "
            "because they are marked for follow-up."
        )
    return 0


def actions_restore_archive_command(client_secret: Path, message_id: str) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    client = GmailClient(token)
    try:
        restored = restore_archived_message(client, state, message_id)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    write_state(state_path(), state)
    if restored:
        print(f"Restored {message_id} to inbox by adding Gmail's INBOX label.")
    else:
        print(f"Message {message_id} is already in the inbox.")
    return 0


def actions_restore_trash_command(client_secret: Path, message_id: str) -> int:
    token = read_token(token_path())
    if token is None:
        print(
            "No Gmail token found. Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1
    if GMAIL_MODIFY_SCOPE not in token.scope.split():
        print(
            "Stored Gmail token does not include gmail.modify. "
            "Run `mailwyrm auth --scope modify` first.",
            file=sys.stderr,
        )
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    state = read_state(state_path())
    client = GmailClient(token)
    try:
        restored = restore_trashed_message(client, state, message_id)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    write_state(state_path(), state)
    if restored:
        print(
            f"Restored {message_id} from trash to inbox by removing Gmail's "
            "TRASH label and adding INBOX."
        )
    else:
        print(f"Message {message_id} is not in trash.")
    return 0


def list_command(limit: int, show_classification: bool, mailbox: str) -> int:
    state = read_state(state_path())
    messages = [
        message
        for message in sorted(
            state.messages.values(),
            key=lambda message: message.internal_date or "",
            reverse=True,
        )
        if message_matches_mailbox(message, mailbox)
    ]
    if not messages:
        print(
            f"No local {mailbox} messages. Run `mailwyrm sync --mailbox {mailbox}` first."
        )
        return 0

    for message in messages[:limit]:
        subject = message.headers.get("Subject", "(no subject)")
        sender = message.headers.get("From", "(unknown sender)")
        fields = [message.id, sender, subject]
        if show_classification:
            classification = state.classifications.get(message.id)
            if classification:
                classification = effective_classification(
                    classification,
                    state.corrections.get(message.id),
                )
                fields.extend([classification.category, classification.reason])
            else:
                fields.extend(["unclassified", ""])
        print("\t".join(fields))
    return 0


def message_matches_mailbox(message: MessageRecord, mailbox: str) -> bool:
    if mailbox == "all-mail":
        return True
    label_ids = set(message.label_ids)
    if mailbox == "trash":
        return "TRASH" in label_ids
    return "INBOX" in label_ids
