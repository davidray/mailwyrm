# Digest Preview Spike

This spike renders a local machine-mail digest from synced and classified Gmail metadata.

It intentionally does not write Gmail labels, archive, trash, mark read, or mutate mailbox state.

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

