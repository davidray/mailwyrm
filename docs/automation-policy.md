# Automation Policy

Mailwyrm keeps a local automation policy in `state.json`.

The initial policy is intentionally conservative:

- `archive_after_digest` is enabled.
- `trash_after_digest` is disabled.

Check the current policy:

```sh
uv run mailwyrm policy status
```

This command is read-only. It does not call Gmail and does not mutate local state.

Enable the local trash policy:

```sh
uv run mailwyrm policy enable-trash-after-digest --confirm-trash-policy
```

This writes local policy only. It does not call Gmail, trash messages, archive messages, label messages, or change message state.

Trash automation remains behind an explicit trust boundary. Trash apply requires local policy opt-in before calling Gmail's trash operation.

After policy opt-in, preview eligible trash candidates without mutating Gmail:

```sh
uv run mailwyrm actions preview-trash --limit 10
```

Apply eligible trash candidates:

```sh
uv run mailwyrm actions apply-trash --limit 10 --client-secret /path/to/client_secret.json
```

Trash apply prints the same policy-gated report before mutating Gmail. It only moves messages to Gmail Trash when policy is enabled, the planner chooses `trash_after_digest`, and the message has appeared in a local digest audit event.
