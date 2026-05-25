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

Archive apply and archive restore write local audit events. A later trash command must require explicit local policy opt-in, Gmail confirmation, and an audit event before changing Gmail state. Use `mailwyrm policy status` to inspect the current policy boundary.
