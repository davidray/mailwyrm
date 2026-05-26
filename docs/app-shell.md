# App Shell

`mailwyrm app` runs the first read-only local Mailwyrm application.

It serves a browser dashboard for the daily cockpit from local state. It does not call Gmail, mutate local state, classify mail, apply labels, archive messages, or move messages to Trash.

Example:

```sh
uv run mailwyrm app
uv run mailwyrm app --mailbox all-mail --limit 50 --audit-limit 25
```

By default the app listens at `http://127.0.0.1:8766`.

The app exposes:

- `/`: the dashboard UI.
- `/api/daily-cockpit`: structured JSON for the same daily cockpit data.
- `/healthz`: a lightweight health check.

## Current Scope

The first app shell is intentionally an attention dashboard, not a full mailbox client.

It shows:

- Account and sync state.
- Human, machine, and needs-review counts.
- Primary attention lanes for human correspondence and protected or uncertain messages.
- Archive and trash policy state.
- Machine digest items with Gmail links.
- Mailbox action previews.
- Policy-gated trash previews.
- Recent Gmail mutation audit events.
- Useful CLI commands for the next explicit workflow step.

## Trust Boundary

The app is read-only. Gmail remains the source of truth, and mailbox mutation still happens through explicit CLI commands that print their preview reports before applying changes.
