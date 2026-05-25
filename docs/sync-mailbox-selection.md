# Sync Mailbox Selection

Mailwyrm sync defaults to inbox-only behavior for daily triage.

For longer-term cleanup workflows, sync can explicitly include archived mail by using all-mail mode.

## Commands

Daily inbox sync:

```sh
uv run mailwyrm sync --mailbox inbox --limit 25 --client-secret /path/to/client_secret.json
```

Longer cleanup sync:

```sh
uv run mailwyrm sync --mailbox all-mail --limit 500 --client-secret /path/to/client_secret.json
```

## Behavior

- `inbox`: fetches messages with the Gmail `INBOX` label.
- `all-mail`: fetches messages without an `INBOX` label filter, so archived mail can be included.

The default is `inbox`.

When a fetched Gmail message already exists in the local index, Mailwyrm replaces the local message metadata with the latest Gmail record. That includes Gmail label IDs, so labels added or removed in Gmail are refreshed locally on the next sync that includes the message.

All-mail sync still only updates Mailwyrm's local index. It does not archive, trash, label, mark read, or otherwise mutate Gmail.
