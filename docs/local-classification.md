# Local Classification Spike

This spike adds a non-destructive classification layer on top of the read-only Gmail index.

It intentionally does not write Gmail labels, archive, trash, or mutate mailbox state.

## What It Does

- Classifies locally indexed messages as `human`, `machine`, or `needs_review`.
- Stores classification output in the local Mailwyrm state file.
- Uses a deterministic rules-based baseline so tests and behavior are stable.
- Uses opt-in synced body text as an additional signal when `body_text` is present.
- Exposes classifications through the CLI.
- Classifies machine mail into durable `machine_type` buckets:
  `marketing`, `transactional`, `news`, `spam`, and `product_community`.

## Commands

```sh
uv run mailwyrm sync --client-secret /path/to/client_secret.json --limit 25
uv run mailwyrm classify
uv run mailwyrm list --show-classification
```

## Classification Shape

Each classification stores:

- `category`
- `machine_type`
- `importance`
- `automation_safety`
- `confidence`
- `reason`
- `suggested_actions`
- `classifier_version`

This matches the project AI behavior contract closely enough that a later LLM-backed classifier can replace or augment the rules engine without changing the local state shape.

## Safety

High-risk machine-generated mail, such as password, payment, banking, legal, tax, insurance, medical, and security mail, is classified as `needs_review` with low automation safety.

Low-risk Copilot notifications from `notifications@github.com` are classified
as `product_community` machine mail with high automation safety and `digest`
plus `trash` suggested actions. High-risk terms still override this rule and
protect the message from trash automation.
