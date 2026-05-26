# Mailwyrm Todo

This is the durable project todo list for work that should outlive any single Codex session.

## Backend And User Experience

These items remain as the app shell starts turning the CLI cockpit into a visible product surface.

1. Gmail history reconciliation.
   - Use Gmail history IDs to reconcile mailbox changes incrementally.
   - Detect remote archive, trash, label, read/unread, and delete changes.
   - Recover cleanly from missed sync windows with periodic reconciliation.
   - Keep Gmail as the source of truth when local and remote state disagree.

2. Thread and body depth for summaries.
   - Fetch enough message and thread body content to produce useful digest summaries.
   - Keep content collection intentionally minimal and tied to user consent.
   - Preserve headers, snippets, and links needed for auditability.
   - Avoid storing unnecessary sensitive content.

3. Operational polish.
   - Add clearer token and scope status commands.
   - Improve Gmail API error messages with likely fixes.
   - Make testing commands easier to discover from the CLI.
   - Surface sync state, last mailbox scope, and account identity in a concise status view.
   - After Gmail API mutations, tell the user that Gmail web UI may need a refresh before moved, archived, trashed, or labeled messages visibly update.
