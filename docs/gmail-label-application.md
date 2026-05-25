# Gmail Label Application

Mailwyrm can preview and explicitly apply Gmail-visible labels from local classifications.

This is still non-destructive. It does not archive, trash, mark read, or remove labels.

## Commands

Preview labels from local classifications:

```sh
uv run mailwyrm labels preview
uv run mailwyrm labels preview --limit 10
uv run mailwyrm labels preview --mailbox all-mail --limit 500
```

Apply labels to Gmail messages:

```sh
uv run mailwyrm labels apply --limit 10 --client-secret /path/to/client_secret.json
uv run mailwyrm labels apply --mailbox all-mail --limit 500 --client-secret /path/to/client_secret.json
```

The apply command prints the same label plan report as preview before mutating Gmail.

The default mailbox scope is `inbox`. Use `all-mail` explicitly for cleanup workflows that include archived messages.

The apply command requires a token with `gmail.modify`:

```sh
uv run mailwyrm auth --scope modify --client-secret /path/to/client_secret.json
```

## Label Mapping

- `human` -> `Mailwyrm/Human`
- `machine` -> `Mailwyrm/Machine`
- `needs_review` -> `Mailwyrm/Needs Review`

High-risk `needs_review` messages also receive:

- `Mailwyrm/Protected`

## Audit Trail

Each applied label mutation writes a local audit event with:

- message ID
- action
- label names
- Gmail label IDs
- classification reason
- classifier version
- timestamp

This keeps Gmail-visible state traceable back to the classifier or user correction that caused it.
