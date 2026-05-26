# Mailbox Action Preview

Mailwyrm can preview mailbox actions from local classifications without mutating Gmail.

This is a trust-building step before archive or trash automation. It proposes what Mailwyrm would do under an approved policy, but it does not archive, trash, mark read, remove labels, or otherwise change Gmail.

## Command

Preview actions for inbox messages:

```sh
uv run mailwyrm actions preview
uv run mailwyrm actions preview --limit 25
```

Preview actions for the wider local index, including archived messages:

```sh
uv run mailwyrm actions preview --mailbox all-mail --limit 500
```

The default mailbox scope is `inbox`.

## Trash Preview

Mailwyrm can preview `trash_after_digest` candidates without mutating Gmail:

```sh
uv run mailwyrm actions preview-trash --limit 10
uv run mailwyrm actions preview-trash --mailbox all-mail --limit 100
```

This command is read-only. It does not call Gmail, trash messages, archive messages, label messages, or write local state.

Trash preview is gated by local automation policy and digest audit state. A message appears only when:

- Local `trash_after_digest` policy is enabled.
- The action planner chooses `trash_after_digest`.
- The message has appeared in a local digest audit event.
- The message is included by the selected mailbox scope.

If trash policy is disabled, the report says so and shows how many trash candidates were skipped by policy.

## Archive Apply

Mailwyrm can apply only `archive_after_digest` plans:

```sh
uv run mailwyrm actions apply-archive --limit 10 --client-secret /path/to/client_secret.json
```

This command prints an action report before mutating Gmail. The report says Gmail will be modified after the preview, then the command archives by removing Gmail's `INBOX` label from messages whose planned action is `archive_after_digest` and that have already appeared in a local digest. Applying `Mailwyrm/Digested` makes that digest state visible in Gmail, but archive eligibility is based on Mailwyrm's local digest audit events.

It does not apply `trash_after_digest`, `protect`, `review`, or `keep` plans. It does not trash messages.

The apply command requires a token with `gmail.modify`:

```sh
uv run mailwyrm auth --scope modify --client-secret /path/to/client_secret.json
```

## Archive Restore

Mailwyrm can restore a previously archived local message to the Gmail inbox by message ID:

```sh
uv run mailwyrm actions restore-archive <gmail-message-id> --client-secret /path/to/client_secret.json
```

This re-adds Gmail's `INBOX` label, updates the local message labels, and writes a local audit event. It does not remove Mailwyrm classification labels or change the message's classification.

The message must already exist in the local Mailwyrm index. If Gmail has changed independently, run sync again to refresh local labels from Gmail.

## Trash Restore

Mailwyrm can restore a previously trashed local message to the Gmail inbox by message ID:

```sh
uv run mailwyrm actions restore-trash <gmail-message-id> --client-secret /path/to/client_secret.json
```

This removes Gmail's `TRASH` label, adds Gmail's `INBOX` label when needed, updates the local message labels, and writes a local audit event. It does not remove Mailwyrm classification labels or change the message's classification.

The message must already exist in the local Mailwyrm index and must currently have the `TRASH` label locally. If Gmail has changed independently, run sync again to refresh local labels from Gmail.

To test this with a message already in Gmail Trash, sync Trash first:

```sh
uv run mailwyrm sync --mailbox trash --limit 25 --client-secret /path/to/client_secret.json
uv run mailwyrm list --mailbox trash --limit 25
```

## Action Vocabulary

- `keep`: human correspondence should stay foregrounded.
- `review`: classification is not safe enough for automation.
- `protect`: important or low-safety mail should be protected from automation.
- `archive_after_digest`: machine mail can leave the inbox after it appears in a digest under an approved policy.
- `trash_after_digest`: low-importance, high-safety, high-confidence machine mail could be trashed after digest under an approved policy.

## Current Safety Rules

The preview is intentionally conservative:

- Human mail is kept.
- High-importance, low-safety, or explicitly protected mail is protected.
- Low-confidence mail is sent to review.
- Machine mail defaults to `archive_after_digest`.
- `trash_after_digest` only appears for low-importance machine mail with high automation safety, high confidence, and an explicit `trash` suggested action.
- Archive apply skips messages that have not yet been recorded in a local digest audit event.
- Trash preview skips messages unless local trash policy is enabled and the message has appeared in a local digest audit event.

Archive apply, archive restore, and trash restore write local audit events. A later trash command must require explicit local policy opt-in, Gmail confirmation, and an audit event before changing Gmail state. Use `mailwyrm policy status` to inspect the current policy boundary.
