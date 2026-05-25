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

## Action Vocabulary

- `keep`: human correspondence should stay foregrounded.
- `review`: classification is not safe enough for automation.
- `protect`: important or low-safety mail should be protected from automation.
- `archive_after_digest`: machine mail could leave the inbox after it appears in a digest under an approved policy.
- `trash_after_digest`: low-importance, high-safety, high-confidence machine mail could be trashed after digest under an approved policy.

## Current Safety Rules

The preview is intentionally conservative:

- Human mail is kept.
- High-importance, low-safety, or explicitly protected mail is protected.
- Low-confidence mail is sent to review.
- Machine mail defaults to `archive_after_digest`.
- `trash_after_digest` only appears for low-importance machine mail with high automation safety, high confidence, and an explicit `trash` suggested action.

These are plans only. A later apply command must require explicit user policy, Gmail confirmation, and an audit event before changing Gmail state.
