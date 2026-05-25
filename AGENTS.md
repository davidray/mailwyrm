# Mailwyrm Agent Guide

This repo contains the product memory for Mailwyrm, an AI-first Gmail client.

Before making product or architecture changes, read:

1. [README.md](README.md)
2. [docs/product-brief.md](docs/product-brief.md)
3. [docs/architecture.md](docs/architecture.md)
4. [docs/ai-behavior.md](docs/ai-behavior.md)
5. [docs/decisions/0001-gmail-is-source-of-truth.md](docs/decisions/0001-gmail-is-source-of-truth.md)

## Non-Negotiable Product Assumptions

- Gmail is the source of truth for mailbox state.
- Mailwyrm is an attention layer, not a replacement mailbox.
- Human correspondence should be foregrounded.
- Machine correspondence should be classified, summarized, and handled through explicit policy.
- Destructive automation must be confidence-based, user-approved, and auditable.
- Important machine mail must be protected from casual deletion.

## Engineering Bias

- Prefer Gmail API primitives over local-only mailbox state.
- Keep labels and actions visible in Gmail when possible.
- Separate AI judgment from mailbox mutation.
- Record why automated actions happened.
- Design sync to tolerate missed, duplicate, and delayed events.

## Pull Requests

- Open PRs as ready for review unless the user explicitly asks for a draft.

## When Adding Features

For any meaningful feature, update the docs if it changes:

- Product promise.
- Gmail sync behavior.
- AI classification behavior.
- Automation or deletion policy.
- User trust, privacy, or auditability.

If a decision changes a durable assumption, add or update an ADR in `docs/decisions/`.
