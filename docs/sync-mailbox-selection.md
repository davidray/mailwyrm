# Sync Mailbox Selection

Mailwyrm sync defaults to inbox-only behavior for daily triage.

For longer-term cleanup workflows, sync can explicitly include archived mail by using all-mail mode. For restore testing and repair workflows, sync can explicitly include Trash by using trash mode.

## Commands

Daily inbox sync:

```sh
uv run mailwyrm sync --mailbox inbox --limit 25 --client-secret /path/to/client_secret.json
```

Longer cleanup sync:

```sh
uv run mailwyrm sync --mailbox all-mail --limit 500 --client-secret /path/to/client_secret.json
```

Trash repair sync:

```sh
uv run mailwyrm sync --mailbox trash --limit 25 --client-secret /path/to/client_secret.json
uv run mailwyrm list --mailbox trash --limit 25
```

## Behavior

- `inbox`: fetches messages with the Gmail `INBOX` label.
- `all-mail`: fetches messages without an `INBOX` label filter, so archived mail can be included.
- `trash`: fetches messages with the Gmail `TRASH` label and asks Gmail to include Trash in list results.

The default is `inbox`.

When a fetched Gmail message already exists in the local index, Mailwyrm replaces the local message metadata with the latest Gmail record. That includes Gmail label IDs, so labels added or removed in Gmail are refreshed locally on the next sync that includes the message.

All sync modes only update Mailwyrm's local index. They do not archive, trash, label, mark read, or otherwise mutate Gmail.
