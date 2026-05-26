# Daily Workflow

`mailwyrm daily preview` renders the first single-report daily machine-mail workflow.

It is intentionally preview-only. It does not mark messages as digested, apply Gmail labels, archive messages, trash messages, or write local audit events.

The report combines:

- The local machine-mail digest.
- Gmail `Mailwyrm/Digested` label candidates from existing local digest audit events.
- Mailbox action candidates for the selected mailbox scope.

The default mailbox scope for mailbox actions is `inbox`, matching Mailwyrm's attention-first default. Use `--mailbox all-mail` when reviewing long-term cleanup candidates outside the inbox.

Example:

```sh
uv run mailwyrm daily preview --limit 25
uv run mailwyrm daily preview --mailbox all-mail --limit 100
```

Archive apply remains gated to messages that have already appeared in a digest. The daily preview may show archive candidates, but the Gmail-mutating archive command will still skip candidates that lack a local digest audit event.

## Apply

`mailwyrm daily apply` performs the conservative daily workflow in one command:

1. Render the combined daily report.
2. Mark included digest items in the local audit log.
3. Apply the Gmail-visible `Mailwyrm/Digested` label.
4. Archive eligible `archive_after_digest` messages by removing Gmail's `INBOX` label.

It does not apply `trash_after_digest`. Trash remains a future explicit-policy step.

Example:

```sh
uv run mailwyrm daily apply --limit 25 --client-secret /path/to/client_secret.json
```

The apply command requires a stored Gmail token with `gmail.modify`, because it may apply labels and archive messages in Gmail. It prints the same combined daily report before mutating Gmail. For apply, the report is rendered from a projected local state that includes the digest audit marks the command is about to write, so the digested-label section reflects the labels that can be applied during the same run.

## Status

`mailwyrm daily status` is a read-only local audit dashboard. It does not call Gmail and does not mutate local state.

It summarizes:

- Indexed and classified message counts.
- Digest audit events and recent digest dates.
- Gmail mutation audit events for digested labels, archive, trash, archive restore, and trash restore.
- Current mailbox action counts for protect, review, archive-after-digest, and trash-after-digest candidates.

Example:

```sh
uv run mailwyrm daily status
uv run mailwyrm daily status --mailbox all-mail
```

For the most recent mutation-level rows, use:

```sh
uv run mailwyrm actions audit
uv run mailwyrm actions audit --limit 100
```
