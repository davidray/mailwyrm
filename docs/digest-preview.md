# Digest Preview Spike

This spike renders a local machine-mail digest from synced and classified Gmail metadata.

It intentionally does not write Gmail labels, archive, trash, mark read, or mutate Gmail mailbox state.

## Commands

```sh
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25
uv run mailwyrm classify
uv run mailwyrm digest
uv run mailwyrm digest --output /tmp/mailwyrm-digest.md
```

## Included Items

The digest includes:

- Messages classified as `machine`.
- High-importance `needs_review` messages so sensitive machine-generated mail is visible rather than hidden.

Human messages are excluded.

## Digest Shape

The Markdown digest groups items into:

- Transactional.
- Deliveries.
- Newsletters.
- Security and account.
- Notifications.
- Needs review.

Each item includes a Gmail link, sender, importance, automation safety, confidence, reason, and snippet.

When a digest is rendered, Mailwyrm records local digest audit events for the messages included in that digest. Archive automation uses those local events as a gate, so `archive_after_digest` messages are not archived until they have appeared in a digest.

## Gmail Digested Labels

After rendering a digest, Mailwyrm can make that local digest state visible in Gmail by applying `Mailwyrm/Digested` to messages with digest audit events.

Preview digested labels:

```sh
uv run mailwyrm digest labels preview
```

Apply digested labels:

```sh
uv run mailwyrm digest labels apply --client-secret /path/to/client_secret.json
```

The apply command prints the same preview report before mutating Gmail. It only applies `Mailwyrm/Digested`; it does not archive, trash, mark read, or change classification labels.
