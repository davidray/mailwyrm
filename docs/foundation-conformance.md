# Foundation Conformance

Bookwyrm Mail follows `bookwyrm-foundation` as the canonical source for
ecosystem philosophy, tone, design principles, AI governance, stewardship,
trust, product taxonomy, and agent behavior.

Broad ecosystem guidance lives in `../bookwyrm-foundation`. This repository
should document Mail-specific implementation details: architecture, commands,
setup, testing, Gmail sync behavior, mailbox action boundaries, AI
classification behavior, automation policy, auditability, and Mail-specific UX.

Run a foundation alignment sweep when major Mail docs change, especially:

- `README.md`
- `AGENTS.md`
- files under `codex/`
- product brief, architecture, AI behavior, Gmail sync, automation policy, or
  ADR docs

Use the foundation checklist at:

```text
../bookwyrm-foundation/templates/foundation-conformance-checklist.md
```

Do not copy broad foundation philosophy into this repo. Link to foundation and
keep local docs focused on Mail implementation.
