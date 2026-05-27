# Gmail Label Setup

Mailwyrm labels are Gmail-visible labels used to keep classification state understandable and repairable in Gmail.

This setup step is explicit. It creates labels only; it does not apply labels to messages, archive messages, trash messages, or change read state.

## Labels

- `Mailwyrm/Human`
- `Mailwyrm/Machine`
- `Mailwyrm/Needs Review`
- `Mailwyrm/Digested`
- `Mailwyrm/Protected`
- `Mailwyrm/Follow Up`

## Commands

Re-authorize with Gmail modify scope:

```sh
uv run mailwyrm auth --scope modify --client-secret /path/to/client_secret.json
```

Create any missing Mailwyrm labels:

```sh
uv run mailwyrm ensure-labels --client-secret /path/to/client_secret.json
```

## Scope

This command requires:

```text
https://www.googleapis.com/auth/gmail.modify
```

Mailwyrm should continue using read-only flows for sync. The modify scope is introduced only for explicit Gmail-visible state changes.
