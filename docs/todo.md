# Mailwyrm Todo

This is the durable project todo list for work that should outlive any single Codex session.

## Backend And User Experience

These items remain as the app shell starts turning the CLI cockpit into a visible product surface.

1. Gmail history reconciliation.
   - Expand the first `sync-history` command beyond known-message label and
     delete reconciliation.
   - Fetch newly seen messages from history where appropriate.
   - Recover cleanly from missed sync windows with periodic reconciliation.
   - Keep Gmail as the source of truth when local and remote state disagree.

2. Thread and body depth for summaries.
   - Expand beyond opt-in bounded single-message body text toward enough thread
     content to produce useful digest summaries.
   - Keep content collection intentionally minimal and tied to user consent.
   - Preserve headers, snippets, and links needed for auditability.
   - Avoid storing unnecessary sensitive content.

3. Operational polish.
   - Add clearer token and scope status commands.
   - Improve Gmail API error messages with likely fixes.
   - Make testing commands easier to discover from the CLI.
   - Surface sync state, last mailbox scope, and account identity in a concise status view.
   - After Gmail API mutations, tell the user that Gmail web UI may need a refresh before moved, archived, trashed, or labeled messages visibly update.

4. Gmail spam and unsubscribe workflow.
   - Add an explicit Gmail-mutating spam action for messages the user classifies
     as Spam.
   - Report or move confirmed spam to Gmail Spam rather than only moving it to
     Trash.
   - Detect trustworthy unsubscribe options, such as `List-Unsubscribe`, and
     attempt unsubscribe only through safe, auditable flows.
   - Keep unsubscribe attempts user-approved until the trust boundary is clear.
