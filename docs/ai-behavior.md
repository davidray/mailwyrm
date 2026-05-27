# AI Behavior

## Classification Contract

The classifier should return:

- `category`: `human`, `machine`, or `needs_review`.
- `machine_type`: optional structured subtype for machine mail. Current
  canonical machine types are `marketing`, `transactional`, `news`, `spam`,
  and `product_community`.
- `review_type`: optional structured subtype for `needs_review` mail. Current
  canonical review types are `security`, `finance`, `legal`, `medical`,
  `account_access`, `travel`, `possible_human`, `uncertain_machine`, and
  `unknown`.
- `importance`: low, medium, or high.
- `automation_safety`: low, medium, or high.
- `confidence`: numeric score.
- `reason`: short explanation suitable for audit UI.
- `suggested_actions`: label, archive, digest, trash, protect, or review.

The model should prefer `needs_review` when confidence is low or consequences are high.

## Risk Rules

Machine-generated mail should not be treated as disposable by default.

High-risk topics include:

- Banking and payments.
- Security alerts.
- Password resets and account recovery.
- Legal, tax, insurance, medical, and government mail.
- Domain renewals and infrastructure alerts.
- Travel disruptions.
- Human replies hidden inside automated systems.

High-risk messages may still be summarized, but should not be auto-trashed without explicit user policy.

## Digest Principles

The daily digest should optimize for decisions, not prose volume.

Good digest items include:

- What changed.
- Why it matters.
- Deadline or date.
- Amount of money if relevant.
- Sender or service.
- Link to original message.
- Suggested next action.

Avoid vague summaries such as "You received an update from..." when the message contains concrete information.

## Policy Learning

Mailwyrm may suggest durable policies based on repeated user behavior, but the user should approve policies before they cause destructive actions.

Example policies:

- Archive transactional records after summarization, but do not trash them.
- Summarize and trash approved spam after the daily digest.
- Always keep security alerts visible.
- Treat product community notifications from known projects as useful background.
- Never auto-trash mail from specified senders or domains.

## Tone

AI explanations should be brief, calm, and operational.

The system should not pretend to be certain when it is making a probabilistic judgment. Use concise explanations like:

- "Automated receipt from a known merchant."
- "Security-related account alert; protected from auto-trash."
- "Looks like a personal reply despite coming through a notification system."
