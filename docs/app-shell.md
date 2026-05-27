# App Shell

`mailwyrm app` runs the first local Mailwyrm application.

It serves a browser dashboard for the daily cockpit from local state. It can classify locally indexed messages into Mailwyrm state, but it does not call Gmail, apply labels, archive messages, or move messages to Trash.

Example:

```sh
uv run mailwyrm app
uv run mailwyrm app --mailbox all-mail --limit 50 --audit-limit 25
uv run mailwyrm app --client-secret /path/to/client_secret.json
```

By default the app listens at `http://127.0.0.1:8766`.
If `--client-secret` is provided, or `MAILWYRM_CLIENT_SECRET` is set, the
cockpit payload includes Gmail CLI commands with that path instead of a
placeholder.

The app exposes:

- `/`: the dashboard UI.
- `/api/daily-cockpit`: structured JSON for the same daily cockpit data.
- `/api/message-detail`: read-only local message detail from indexed state.
- `/api/workflow-preview`: read-only local reports for preview workflows.
- `/api/local-classify`: local-only classification for indexed messages.
- `/healthz`: a lightweight health check.

## Current Scope

The first app shell is intentionally an attention dashboard, not a full mailbox client.

It shows:

- Account and sync state.
- Human, machine, and needs-review counts.
- A prominent cleanup band for archive-ready and trash-ready inbox candidates,
  including messages that need digest or policy gates before Gmail mutation.
- Primary attention lanes for human correspondence and protected or uncertain
  messages, including review-type buckets for needs-review mail.
- Archive and trash policy state.
- Machine digest items with Gmail links.
- Local message detail for lane, digest, and action-preview items.
- Mailbox action previews.
- Policy-gated trash previews.
- Recent Gmail mutation audit events.
- Preview-first workflow controls for local classification, daily preview,
  label preview, archive preview, and trash preview.
- In-app read-only preview reports for daily preview, label preview, mailbox
  action preview, and trash preview.
- In-app local classification for indexed messages in the selected mailbox scope.

## Trust Boundary

The app can write local Mailwyrm classification state for indexed messages. It may also render local preview reports from indexed Mailwyrm state. It does not call Gmail, apply labels, archive messages, move messages to Trash, or otherwise mutate mailbox state. Gmail remains the source of truth, and mailbox mutation still happens through explicit CLI commands that print their preview reports before applying changes.
