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

Trash automation remains behind an explicit trust boundary. A future trash command must require local policy opt-in before calling Gmail's trash operation.
