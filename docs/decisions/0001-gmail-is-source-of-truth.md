# ADR 0001: Gmail Is The Source Of Truth

## Status

Accepted

## Context

The intended user uses Gmail as their email service and has been disappointed by clients that do not stay in sync with Gmail. A core requirement is that archiving, trashing, labeling, reading, and other mailbox actions remain consistent with Gmail.

An AI-first email client will need local state for classification, summaries, policies, and audit logs. That local state must not turn into a competing mailbox model.

## Decision

Mailwyrm will treat Gmail as the authoritative source of mailbox state.

Mailwyrm may maintain local indexes and derived metadata, but message state changes must be represented through Gmail operations whenever possible.

## Consequences

Benefits:

- User actions remain visible in Gmail.
- Gmail remains usable as a fallback client.
- Trust is easier to earn because Mailwyrm does not trap mail in a private system.
- Sync bugs can be repaired by reconciling against Gmail.

Costs:

- Mailwyrm must model Gmail labels and thread semantics carefully.
- Some product ideas may need to be represented as Mailwyrm metadata rather than Gmail state.
- Sync code must handle duplicate events, missed notifications, and reconciliation.
- Gmail API permissions and verification may become product constraints.

## Implementation Guidance

- Archive by removing `INBOX`.
- Trash by using Gmail's trash operation.
- Keep Mailwyrm labels visible in Gmail.
- Store Gmail message IDs, thread IDs, labels, and sync cursors.
- Track pending local operations until confirmed by Gmail.
- Keep an audit log for every AI-assisted mutation.

