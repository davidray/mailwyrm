# Product Brief

## Problem

Email mixes human obligations with machine-generated noise. A message from a friend, a delivery receipt, a bank alert, a newsletter, and a password reset can all arrive in the same stream with the same visual weight.

Traditional clients improve search, layout, and keyboard flow, but they still ask the user to process the full stream. Mailwyrm should reduce that burden by separating correspondence that deserves attention from correspondence that mainly needs to be recorded, summarized, or discarded later.

## Product Thesis

Mailwyrm is an AI-first Gmail client that treats email as a flow of attention, obligations, relationships, and records.

The client should foreground human correspondence and convert machine correspondence into useful structured summaries. Over time, it should learn user-approved policies for what can be archived, summarized, kept, or moved to Trash.

## Target Experience

When the user opens Mailwyrm, they should primarily see:

- People who need a response.
- People the user is waiting on.
- Human conversations with new activity.
- A daily summary of machine correspondence.
- Important machine-generated events that require action.

The user should not need to manually triage routine receipts, shipping notices, SaaS updates, newsletters, or alert noise every day.

## Human vs Machine

Human correspondence:

- Personal messages.
- Direct replies.
- Work conversations.
- Small-group threads.
- Messages where a person likely expects the user to read or respond.

Machine correspondence:

- Receipts and invoices.
- Shipping and delivery notifications.
- Newsletters and marketing.
- Account, security, and policy notifications.
- SaaS alerts and automated reports.
- Calendar, travel, finance, and subscription updates.

Useful machine-mail buckets include marketing, transactional, news, spam, and
product community mail. These categories should describe how the user is likely
to treat the message, not merely which system generated it.

Machine does not mean unimportant. A bank fraud alert is machine correspondence, but it should be treated as high importance and low automation safety.

Needs-review mail should also be structured. Useful review buckets include
security, finance, legal, medical, account access, travel, possible human,
uncertain machine, and unknown. These buckets help the app explain why mail is
protected before the user resolves it into human correspondence, machine
correspondence, or a durable policy.

## Daily Machine Digest

The digest should be structured rather than a flat list of summaries.

Useful categories include:

- Purchases and receipts.
- Deliveries and shipping changes.
- Bills, renewals, and subscription notices.
- Security and account alerts.
- Calendar, travel, and event updates.
- Newsletters worth reading.
- Low-value mail handled automatically.

Each digest item should link back to the original Gmail message or Mailwyrm thread view.

## Automation Trust Ladder

Mailwyrm should earn automation trust gradually.

Phase 1: classify only. No mailbox mutation beyond optional labels.

Phase 2: archive obvious machine mail with user approval.

Phase 3: trash approved low-risk machine mail after it appears in the daily digest.

Phase 4: suggest durable policies based on repeated user behavior.

## What Makes It Special

Mailwyrm should not feel like a chatbot sitting next to an inbox. It should feel like the inbox has a thoughtful chief of staff.

The special parts are:

- Relationship-first views rather than message-first views.
- Confidence-based automation.
- Gmail-native sync.
- Durable user-approved policy.
- Auditable AI decisions.
- Daily machine-mail compression.
- Separation of attention from record keeping.
