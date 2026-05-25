from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mailwyrm import __version__
from mailwyrm.classifier import classify_message
from mailwyrm.config import state_path, token_path
from mailwyrm.digest import render_digest
from mailwyrm.gmail import GmailClient
from mailwyrm.models import MessageRecord
from mailwyrm.oauth import add_auth_arguments, authorize, refresh_token, token_is_expired
from mailwyrm.store import read_state, read_token, write_state, write_token


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return auth_command(args.client_secret, args.port)
    if args.command == "sync":
        return sync_command(args.client_secret, args.limit)
    if args.command == "classify":
        return classify_command(args.limit)
    if args.command == "digest":
        return digest_command(args.output)
    if args.command == "list":
        return list_command(args.limit, args.show_classification)

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

    return parser


def auth_command(client_secret: Path, port: int) -> int:
    token = authorize(client_secret, port=port)
    write_token(token_path(), token)
    print(f"Stored Gmail token at {token_path()}")
    return 0


def sync_command(client_secret: Path, limit: int) -> int:
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

    message_refs = client.list_messages(max_results=limit)
    for message_ref in message_refs:
        message = client.get_message_metadata(str(message_ref["id"]))
        record = MessageRecord.from_gmail_message(message)
        state.messages[record.id] = record

    write_state(state_path(), state)
    print(
        f"Synced {len(message_refs)} message(s) for {state.account_email or 'unknown account'}."
    )
    print(f"Local index: {state_path()}")
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
                fields.extend([classification.category, classification.reason])
            else:
                fields.extend(["unclassified", ""])
        print("\t".join(fields))
    return 0
