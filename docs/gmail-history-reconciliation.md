# Gmail History Reconciliation

Mailwyrm can reconcile Gmail message, label, and deletion changes from the
stored Gmail history cursor.

This keeps Gmail as the source of truth when mailbox state changes outside Mailwyrm, such as archiving a message in Gmail, moving it to Trash, marking it unread, or applying labels.

## Command

```sh
uv run mailwyrm sync-history --client-secret /path/to/client_secret.json
uv run mailwyrm sync-history --client-secret /path/to/client_secret.json --max-pages 25
```

Run `mailwyrm sync` first so local state has a Gmail `history_id` cursor.

## App Refresh

The app's top **Refresh** button uses the same reconciliation model.

When a stored Gmail history cursor exists, Refresh reads Gmail history events and
updates local state from those changes. Newly fetched messages are classified
locally before the cockpit reloads.

When no cursor exists, or when Gmail reports that the stored cursor is too old,
Refresh falls back to a full sync for the selected mailbox scope and classifies
unclassified messages. The Tools tab keeps a separate full sync control as an
explicit repair path.

## What It Does

`sync-history` reads Gmail history events after the stored cursor and applies
them to the local Mailwyrm index.

Current behavior:

- Fetches newly seen messages from `messagesAdded` history events.
- Fetches unknown live messages referenced by label events.
- Classifies newly fetched history messages locally so they can appear in the
  app without a separate `mailwyrm classify` step.
- Applies `labelsAdded` events to local `label_ids`.
- Applies `labelsRemoved` events to local `label_ids`.
- Removes locally indexed messages when Gmail reports `messagesDeleted`.
- Advances the stored Gmail history cursor when Gmail returns a newer `historyId`.
- Reports unknown message IDs that could not be fetched or were only seen as
  deleted.
- If Gmail reports that the stored history cursor is too old, falls back to a
  full sync for the last selected mailbox scope and classifies unclassified
  synced messages.

This command is read-only from Gmail's perspective. It does not apply labels, archive, trash, mark read or unread, or otherwise mutate Gmail.

## Current Limitations

History reconciliation still depends on an explicit command or app workflow; it
does not yet run as a background watcher.

Future work should add:

- App-surface status for last reconciliation and missed-history recovery.
