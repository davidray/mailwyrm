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

## User Shortcuts

The user may use short commands for common project workflows:

- `fb`: Review and address pull request feedback for the current branch or explicitly named PR. After fixing and pushing, resolve the GitHub review threads that were actually addressed; leave ambiguous, unfixed, or intentionally deferred threads unresolved and call them out.
- `pr`: Create a ready-for-review pull request for the current branch.
- `rs`: Restart the desktop app, or start it if it is not running. If no desktop app process exists yet, explain that and give the closest available run command.
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
