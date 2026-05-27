# Bookwyrm Mail Realignment

This document records the first philosophical realignment pass for Bookwyrm
Mail after comparing the current app with the Bookwyrm foundation and
Bookwyrm Reader.

Bookwyrm Foundation is now the canonical source for ecosystem philosophy, tone,
visual language, design principles, trust, and AI governance. This document is a
historical product-specific record of Mail drift and follow-up work; it should
not be treated as a replacement for Foundation guidance.

## Areas Of Drift

- The app framed itself as a "Daily cockpit", which suggested operational
  control, metrics, and throughput rather than correspondence stewardship.
- The visual system leaned toward a light SaaS dashboard: bright panels,
  blue links, metric pills, and utility-card density.
- Tools language centered on workflows, action previews, trash previews, and
  audits. The behavior was useful, but the vocabulary made the app feel more
  like infrastructure than an inhabitable communication space.
- Review language emphasized protected or uncertain messages, which was
  accurate but emotionally defensive. The Bookwyrm framing should emphasize
  context and careful judgment.

## Philosophical Inconsistencies

- The product promise is thoughtful communication management, but the first
  screen used productivity-control language.
- Gmail mutation safety was visible, but it was not yet expressed as
  stewardship.
- The UI was increasingly capable but risked becoming an email operations
  dashboard rather than a calm place for correspondence.

## Initial Changes

- Renamed the app heading from "Daily cockpit" to "Correspondence".
- Added a quieter editorial line: "A quieter place to read what matters and
  settle what can wait."
- Changed the primary tab labels from "Real People" and "Daily Digest" to
  "Correspondence" and "Digest".
- Reframed review as "Needs context".
- Reframed tools language around stewardship, proposals, and records.
- Shifted the visual atmosphere toward Bookwyrm Reader: warm dark surfaces,
  paper-like text, moss and brass accents, serif headings, softer panels, and
  reduced dashboard brightness.
- Updated local UI copy so Gmail mutation boundaries are described as a
  boundary, not an app capability boast.

## Unresolved Tensions

- The underlying route and API names still use `daily-cockpit`; renaming those
  would be a broader compatibility change.
- The Tools tab still contains dense operational controls. It remains necessary
  while the app is browser-based, but it should become quieter as the desktop
  wrapper matures.
- Counters remain visible in some places. They are useful for orientation, but
  future passes should ensure they do not become performance pressure.
- "Got it" is useful but casual; it may eventually need language that better
  matches correspondence stewardship.

## Recommendations

- Continue shifting visible language from productivity operations toward
  correspondence, context, stewardship, and records.
- Consider making the Digest feel more editorial: fewer control surfaces, more
  summary rhythm, and clearer separation between reading and clearing.
- Rework Tools into a secondary stewardship area with progressive disclosure
  once Gmail mutation workflows are stable.
- Add a durable product principle: email is correspondence and intellectual
  continuity, not task throughput.
- Preserve evidence and auditability, but present them calmly.
