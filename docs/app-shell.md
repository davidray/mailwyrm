# App Shell

`mailwyrm app` runs the first local Mailwyrm application.

It serves a browser dashboard for the daily cockpit from local state. It can
classify locally indexed messages, save local review resolutions into Mailwyrm
state, and perform explicit user-approved bundle actions when Gmail modify
credentials are configured.

Example:

```sh
uv run mailwyrm app
uv run mailwyrm app --mailbox all-mail --limit 50 --audit-limit 25
uv run mailwyrm app --client-secret /path/to/client_secret.json
uv run mailwyrm app --show-metrics
```

By default the app listens at `http://127.0.0.1:8766`.
If `--client-secret` is provided, or `MAILWYRM_CLIENT_SECRET` is set, the
cockpit payload includes Gmail CLI commands with that path instead of a
placeholder.
Summary metric cards are hidden by default. Use `--show-metrics` or set
`MAILWYRM_SHOW_METRICS=1` to show them while the metrics surface is still being
shaped.

The app exposes:

- `/`: the dashboard UI.
- `/api/daily-cockpit`: structured JSON for the same daily cockpit data.
- `/api/message-detail`: read-only local message detail from indexed state.
- `/api/workflow-preview`: read-only local reports for preview workflows.
- `/api/local-classify`: local-only classification for indexed messages.
- `/api/review-resolution`: local-only review resolution for indexed messages.
- `/api/followup`: local-only follow-up markers for indexed digest messages.
- `/api/machine-bundle/got-it`: explicit Gmail Trash action for a machine-mail
  category bundle.
- `/api/conversation-complete`: explicit Gmail archive action for a human
  conversation thread.
- `/healthz`: a lightweight health check.

## Current Scope

The first app shell is intentionally an attention dashboard, not a full mailbox client.

It is organized around three first-class tabs and one quieter operational tab:

- Real People: human correspondence grouped by person and Gmail thread so
  relationships and conversations are the primary units.
- Daily Digest: machine-mail category summaries.
- Review: protected or uncertain mail that needs triage.
- Tools: lower-prominence operational surfaces for action previews, audit, and
  workflow controls.

It shows:

- Account and sync state behind the profile avatar menu.
- Optional Real People, machine, and needs-review counts behind a feature flag.
- Primary attention lanes for human correspondence and protected or uncertain
  messages, including review-type buckets for needs-review mail.
- A "Complete" action for Real People conversations that archives the Gmail
  thread and removes it from Real People until new inbox activity arrives.
  Multiple indexed messages from the same Gmail thread appear as a single
  conversation row.
- Inline review controls on Review cards so sender-and-subject triage can
  classify mail without opening message details.
- Archive and trash policy state.
- Machine digest bundles grouped by category. Some categories use sender-level
  summary rows, while news stays headline-first so distinct stories do not get
  collapsed under one sender.
- Follow-up toggles on digest rows. Marked messages keep a visible follow-up
  identity and are skipped by digest cleanup until the marker is removed.
- A category-level "Got it" button that records the bundle as digested and
  moves the whole bundle except follow-up messages to Gmail Trash.
- Local message detail for lane, digest, and action-preview items.
- Local review-resolution controls that can turn needs-review mail into Real
  People or a machine digest category, including Spam.
- Mailbox action previews.
- Policy-gated trash previews.
- Recent Gmail mutation audit events.
- Preview-first workflow controls for local classification, daily preview,
  label preview, archive preview, and trash preview.
- In-app read-only preview reports for daily preview, label preview, mailbox
  action preview, and trash preview in the Tools tab.
- In-app local classification and review resolution for indexed messages in
  the selected mailbox scope.

## Trust Boundary

The app can write local Mailwyrm classification, correction, and follow-up
state for indexed messages. It may also render local preview reports from
indexed Mailwyrm state. A category-level "Got it" button is an explicit
user-approved Gmail mutation: when Gmail modify credentials are configured, it
moves every non-follow-up message in that machine-mail bundle to Gmail Trash
and writes local audit events. Completing a Real People conversation is also an explicit
user-approved Gmail mutation: it archives the Gmail thread by removing `INBOX`
and writes local audit events for indexed messages in that thread. Gmail
remains the source of truth, and other mailbox mutations still happen through
explicit CLI commands that print their preview reports before applying changes.
