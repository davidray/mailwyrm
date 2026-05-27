# Mailwyrm Agent Guide

This repo contains the product memory for Bookwyrm Mail, an AI-first Gmail
client within the broader Bookwyrm ecosystem.

## Canonical Foundation

This repository follows the Bookwyrm Foundation documents as the canonical
source for ecosystem philosophy, tone, design principles, AI behavior,
stewardship, and trust. Local guidance in this repository is subordinate to
foundation guidance and should only define product-specific implementation
details.

When making product, design, trust, or AI-behavior changes, defer to the
`bookwyrm-foundation` repository first. This repo should not duplicate broad
Bookwyrm philosophy or design-system guidance; it should describe how those
principles apply to Bookwyrm Mail.

Before making product or architecture changes, read:

1. `bookwyrm-foundation/README.md`
2. `bookwyrm-foundation/INDEX.md`
3. `bookwyrm-foundation/codex/foundational-agent-instructions.md`
4. [README.md](README.md)
5. [docs/product-brief.md](docs/product-brief.md)
6. [docs/architecture.md](docs/architecture.md)
7. [docs/ai-behavior.md](docs/ai-behavior.md)
8. [docs/decisions/0001-gmail-is-source-of-truth.md](docs/decisions/0001-gmail-is-source-of-truth.md)

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

## User Shortcuts

The user may use short commands for common project workflows:

- `fb`: Review and address pull request feedback for the current branch or explicitly named PR. After fixing and pushing, resolve the GitHub review threads that were actually addressed; leave ambiguous, unfixed, or intentionally deferred threads unresolved and call them out.
- `pr`: Create a ready-for-review pull request for the current branch.
- `rs`: Restart the local Mailwyrm app server, or start it if it is not running. Prefer the current app command (`uv run mailwyrm app --port 8766`) and leave the app available at `http://127.0.0.1:8766/`. If a future desktop wrapper exists, restart that wrapper and its app server together.
- `tst`: Prepare the environment for testing and give concise test instructions, including any live Gmail steps when relevant.
- `md`: The work-in-progress PR has been tested and merged; check out `main`, pull the latest changes, and clean up local state where safe.
- `wn`: Answer "What's next?" with the recommended next project step.

Treat these as conversational shortcuts, not shell commands, unless matching executable project commands are added later.

## When Adding Features

For any meaningful feature, update the docs if it changes:

- Product promise.
- Gmail sync behavior.
- AI classification behavior.
- Automation or deletion policy.
- User trust, privacy, or auditability.

If a decision changes a durable assumption, add or update an ADR in `docs/decisions/`.
