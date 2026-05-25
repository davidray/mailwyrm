from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mailwyrm import __version__
from mailwyrm.classifier import classify_message
from mailwyrm.config import state_path, token_path
from mailwyrm.corrections import CorrectionError, add_correction, correction_report
from mailwyrm.corrections import effective_classification
from mailwyrm.digest import render_digest
from mailwyrm.gmail import GmailClient
from mailwyrm.labels import apply_label_plans, build_label_plans, render_label_preview
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
from mailwyrm.store import read_state, read_token, write_state, write_token


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
        return digest_command(args.output)
    if args.command == "correct":
        return correct_command(args)
    if args.command == "corrections":
        return corrections_command()
    if args.command == "list":
        return list_command(args.limit, args.show_classification)
    if args.command == "labels":
        return labels_command(args)

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
        help="Render a local machine-mail digest without mutating Gmail.",
    )
    digest_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the Markdown digest. Prints to stdout by default.",
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
    for message_ref in message_refs:
        message = client.get_message_metadata(str(message_ref["id"]))
        record = MessageRecord.from_gmail_message(message)
        state.messages[record.id] = record

    write_state(state_path(), state)
    print(
        f"Synced {len(message_refs)} {mailbox} message(s) for "
        f"{state.account_email or 'unknown account'}."
    )
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


def digest_command(output: Path | None) -> int:
    state = read_state(state_path())
    if not state.messages:
        print("No local messages. Run `mailwyrm sync` first.", file=sys.stderr)
        return 1
    if not state.classifications:
        print("No local classifications. Run `mailwyrm classify` first.", file=sys.stderr)
        return 1

    digest = render_digest(state)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{digest}\n", encoding="utf-8")
        print(f"Wrote digest to {output}")
    else:
        print(digest)
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
