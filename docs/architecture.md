# Architecture Notes

## Source Of Truth

Gmail is the source of truth for mailbox state.

Mailwyrm may keep a local database for indexing, classification, summaries, audit logs, and sync performance, but it should not become an independent mailbox whose state diverges from Gmail.

## Gmail-Native Actions

Mailwyrm actions should map to Gmail actions.

- Archive: remove the `INBOX` label.
- Trash: call Gmail's trash operation.
- Restore from Trash: remove `TRASH` and apply the appropriate destination labels.
- Mark read/unread: update Gmail message labels.
- Classify: apply Gmail-visible Mailwyrm labels where useful.
- Star or unstar: use Gmail's starred state.

If an action cannot be represented in Gmail, treat it as Mailwyrm metadata and make that boundary explicit.

## Labels

Expected labels:

- `Mailwyrm/Human`
- `Mailwyrm/Machine`
- `Mailwyrm/Needs Review`
- `Mailwyrm/Digested`
- `Mailwyrm/Protected`

Labels should be visible in Gmail so users can understand and repair state outside Mailwyrm.

## Sync Model

The intended sync model is:

1. Perform an initial Gmail sync.
2. Store message IDs, thread IDs, label IDs, internal dates, headers, snippets, and sync cursor state.
3. Use Gmail history IDs and push or polling to detect changes.
4. Reconcile remote Gmail changes into the local index.
5. Treat local mailbox actions as pending operations until Gmail confirms them.
6. Make action failure visible and retry where safe.

The app should be robust to duplicate history events, missed notifications, and out-of-order local state. Periodic reconciliation is expected.

## Local Data

The local database may contain:

- Gmail message and thread identifiers.
- Header metadata.
- Snippets and selected body text needed for classification.
- Classification outputs.
- Summaries.
- User policy.
- Audit events.
- Sync cursors.

Sensitive content should be minimized, encrypted where appropriate, and clearly tied to user consent.

## AI Pipeline

The classification and summarization pipeline should be separate from mailbox mutation.

Recommended flow:

1. Ingest message metadata and content.
2. Classify human, machine, or needs review.
3. Assess risk and confidence.
4. Generate summary fields where appropriate.
5. Propose or apply policy.
6. Execute Gmail action only if policy allows it.
7. Write an audit event.

## Audit Trail

Every AI-assisted mailbox action should record:

- Message ID and thread ID.
- Previous Gmail labels.
- New Gmail labels or action.
- Classification.
- Confidence.
- Policy or rule that allowed the action.
- Timestamp.
- Model or classifier version.
- Undo or remediation path when possible.

