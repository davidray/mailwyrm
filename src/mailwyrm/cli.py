from __future__ import annotations

import argparse
import copy
import sys
from datetime import UTC, datetime
from pathlib import Path

from mailwyrm import __version__
from mailwyrm.actions import (
    apply_archive_action_plans,
    build_action_plans,
    render_action_preview,
    restore_archived_message,
)
from mailwyrm.classifier import classify_message
from mailwyrm.config import state_path, token_path
from mailwyrm.corrections import CorrectionError, add_correction, correction_report
from mailwyrm.corrections import effective_classification
from mailwyrm.daily import render_daily_preview, render_daily_status
from mailwyrm.digest import mark_digest_items, render_digest
from mailwyrm.gmail import GmailClient
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
from mailwyrm.sync import SyncStats, refresh_message_from_gmail, render_sync_summary


SYNC_MAILBOXES = ("inbox", "all-mail")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return auth_command(args.client_secret, args.port, args.scope)
    if args.command == "sync":
        return sync_command(args.client_secret, args.limit, args.mailbox)
    if args.command == "ensure-labels":
        return ensure_labels_command(args.client_secret)
    if args.command == "classify":
        return classify_command(args.limit)
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
        return list_command(args.limit, args.show_classification)
    if args.command == "labels":
        return labels_command(args)
    if args.command == "actions":
        return actions_command(args)

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

    return parser


def auth_command(client_secret: Path, port: int, scope_name: str) -> int:
    token = authorize(client_secret, port=port, scope=scope_for_name(scope_name))
    write_token(token_path(), token)
    print(f"Stored Gmail token at {token_path()}")
    return 0


def sync_command(client_secret: Path, limit: int, mailbox: str) -> int:
    token = read_token(token_path())
    if token is None:
        print("No Gmail token found. Run `mailwyrm auth` first.", file=sys.stderr)
        return 1

    if token_is_expired(token):
        token = refresh_token(client_secret, token)
        write_token(token_path(), token)

    client = GmailClient(token)
    profile = client.profile()
    state = read_state(state_path())
    state.account_email = profile.get("emailAddress")
    state.history_id = profile.get("historyId")
    state.last_sync_mailbox = mailbox

    message_refs = client.list_messages(
        max_results=limit,
        label_ids=label_ids_for_mailbox(mailbox),
    )
    stats = SyncStats()
    for message_ref in message_refs:
        message = client.get_message_metadata(str(message_ref["id"]))
        record = MessageRecord.from_gmail_message(message)
        stats = refresh_message_from_gmail(state, record, stats)

    write_state(state_path(), state)
    print(render_sync_summary(stats, mailbox, state.account_email))
    print(f"Local index: {state_path()}")
    return 0


def label_ids_for_mailbox(mailbox: str) -> tuple[str, ...] | None:
    if mailbox == "all-mail":
        return None
    return ("INBOX",)


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


def classify_command(limit: int | None) -> int:
    state = read_state(state_path())
    messages = sorted(
        state.messages.values(),
        key=lambda message: message.internal_date or "",
        reverse=True,
    )
    if not messages:
        print("No local messages. Run `mailwyrm sync` first.", file=sys.stderr)
        return 1

    selected_messages = messages[:limit] if limit is not None else messages
    for message in selected_messages:
        classification = classify_message(message)
        state.classifications[message.id] = classification

    write_state(state_path(), state)
    print(f"Classified {len(selected_messages)} message(s) locally.")
    return 0


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
    if args.daily_command == "preview":
        return daily_preview_command(args.limit, args.mailbox)
    if args.daily_command == "apply":
        return daily_apply_command(args.client_secret, args.limit, args.mailbox)
    if args.daily_command == "status":
        return daily_status_command(args.mailbox)

    print("Choose `preview`, `apply`, or `status`.", file=sys.stderr)
    return 1


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
    if args.actions_command == "apply-archive":
        return actions_apply_archive_command(
            args.client_secret,
            args.limit,
            args.mailbox,
        )
    if args.actions_command == "restore-archive":
        return actions_restore_archive_command(args.client_secret, args.message_id)

    print("Choose `preview`, `apply-archive`, or `restore-archive`.", file=sys.stderr)
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


def list_command(limit: int, show_classification: bool) -> int:
    state = read_state(state_path())
    messages = sorted(
        state.messages.values(),
        key=lambda message: message.internal_date or "",
        reverse=True,
    )
    if not messages:
        print("No local messages. Run `mailwyrm sync` first.")
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
