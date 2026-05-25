# Gmail Read-Only Sync Spike

This spike proves Mailwyrm can connect to Gmail without introducing a parallel mailbox.

It intentionally does not classify, archive, label, or trash messages yet.

## What It Does

- Runs a local browser OAuth flow with the Gmail read-only scope.
- Stores the OAuth token outside the repository.
- Fetches Gmail profile metadata.
- Fetches recent inbox message metadata.
- Stores a local JSON index of Gmail message IDs, thread IDs, labels, selected headers, snippets, and the current profile history ID.

## Local Files

By default, runtime state is stored in `~/.mailwyrm`.

- `~/.mailwyrm/gmail-token.json`: OAuth token.
- `~/.mailwyrm/state.json`: local read-only Gmail index.

Set `MAILWYRM_HOME` to use a different directory.

## Commands

```sh
uv run mailwyrm auth --client-secret /path/to/client_secret.json
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25
uv run mailwyrm list
```

The Google OAuth client must allow `http://127.0.0.1:8765/oauth2callback` as a redirect URI.

## Scope

The spike uses:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Later PRs can introduce `gmail.modify` when Mailwyrm is ready to apply Gmail-visible labels or mailbox actions.

