# Bookwyrm Mail Realignment Prompt

This prompt captures a product-specific realignment task for Bookwyrm Mail.
Bookwyrm Foundation is the canonical source for ecosystem philosophy, tone,
design principles, AI behavior, stewardship, and trust. Do not duplicate or
reinterpret Foundation guidance here; read it directly and defer to it.

## Required Foundation Context

Before making realignment changes, read the `bookwyrm-foundation` repository:

- `README.md`
- `INDEX.md`
- `codex/foundational-agent-instructions.md`
- The Foundation philosophy, branding, business/trust, AI governance, product
  taxonomy, and design-system documents referenced by `INDEX.md`.

Use Bookwyrm Reader as an experiential reference for how Foundation principles
manifest in a mature product, especially its atmosphere, pacing, reading
ergonomics, interaction restraint, typography, and emotional tone.

## Product-Specific Goal

Evolve Bookwyrm Mail toward thoughtful communication management. The product
should help users maintain calmer relationships with email by separating
correspondence that deserves attention from machine-generated mail that can be
summarized, reviewed, archived, or discarded through explicit policy.

Mail should feel like a natural Bookwyrm product, not a separate productivity
dashboard. Preserve Gmail as the source of truth, preserve user control over
mailbox mutation, and keep AI classification auditable.

## Evaluate Mail-Specific Drift

Review the existing product for places where Bookwyrm Mail drifts toward:

- generic email-client conventions
- dashboard or metric-heavy behavior
- notification-centric UX
- aggressive workflow optimization
- inbox-zero ideology
- unclear Gmail mutation boundaries
- AI decisions that are not explainable or reviewable

Identify Mail-specific terminology, navigation, component behavior, workflow
assumptions, and implementation details that should change.

## Initial Realignment Scope

Do not redesign the product from scratch. Favor small, thoughtful refinements
that improve:

- emotional coherence with Bookwyrm Foundation
- correspondence-first workflow direction
- calm presentation of Gmail actions and auditability
- visual atmosphere where it is clearly product-specific
- AI explanation clarity and user control

## Deliverable

After implementation, summarize:

- areas of Mail-specific drift discovered
- inconsistencies with Foundation guidance
- changes made
- unresolved product tensions
- recommendations for future iterations

The goal is to help Bookwyrm Mail become a coherent Bookwyrm product while
keeping this repository focused on local implementation details.
