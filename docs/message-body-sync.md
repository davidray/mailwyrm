# Message Body Sync

Mailwyrm can optionally collect bounded message body text during Gmail sync.

This is an explicit opt-in because body content is more sensitive than headers and snippets. Normal `mailwyrm sync` still fetches metadata only.

## Command

```sh
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25 --include-body
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25 --include-body --body-char-limit 4000
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25 --include-body --include-thread-context
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25 --include-body --include-thread-context --thread-context-limit 3
```

`--body-char-limit` defaults to `4000` characters per message and must be non-negative. Passing `--include-body --body-char-limit 0` fetches full Gmail messages but stores no body text.

`--include-thread-context` requires `--include-body`. It fetches full Gmail threads for selected messages, then stores only a bounded window of messages from each selected thread as normal bounded `MessageRecord` entries. `--thread-context-limit` defaults to `3` messages per selected thread and must be positive. The selected message is included when Gmail returns it in the thread payload; nearby earlier messages are preferred, with later messages filling any remaining room.

## What Is Stored

When enabled, Mailwyrm extracts text from Gmail `format=full` message payloads:

- Prefer `text/plain` MIME parts.
- Fall back to simple text extracted from `text/html` parts.
- Decode Gmail base64url body payloads.
- Normalize whitespace and HTML entities.
- Truncate to the configured character limit before writing local state.

The extracted text is stored on each local `MessageRecord` as `body_text`.
Later metadata-only syncs preserve previously collected `body_text` for messages that remain in the local index. When thread context is enabled, additional bounded-context messages from the same Gmail thread may be stored even if only one message from that thread was in the selected mailbox page.

Current limitation: Gmail may place larger body parts behind `body.attachmentId` instead of inline `body.data`. Mailwyrm does not fetch those body attachments yet, so some messages may still have empty `body_text` even when `--include-body` is enabled.

## Current Use

Body text is used locally for:

- Classification signals.
- Digest item detail when body text is available.
- Grouped digest summaries that combine sender, subject, and bounded message text.

This does not mutate Gmail. Gmail remains the source of truth for mailbox state.

## Privacy Boundary

Body text collection should remain intentionally minimal and user-initiated. Future work that stores larger bodies, full threads, attachments, or generated summaries should update this document and the project architecture notes.
