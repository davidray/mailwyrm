# Classification Corrections

Classification corrections are local user feedback for improving Mailwyrm's classifier before any Gmail-writing automation exists.

Corrections do not mutate Gmail.

The app can also save local review resolutions for `needs_review` messages.
Those resolutions are stored as corrections and then flow through the normal
mailbox action planner:

- Human: keep foregrounded as human correspondence.
- Protect: keep protected from mailbox automation.
- Archive: treat as machine mail that can archive after digest.
- Trash: treat as low-risk machine mail that can trash after digest, subject to
  the existing digest and policy gates.

Review resolutions still do not mutate Gmail. They only change local Mailwyrm
state until the user runs an explicit Gmail-writing command.

## Commands

```sh
uv run mailwyrm list --show-classification
uv run mailwyrm correct MESSAGE_ID machine --machine-type news --reason "Newsletter from a service"
uv run mailwyrm correct MESSAGE_ID human --reason "Direct note from a person"
uv run mailwyrm corrections
```

Corrected classifications are used by:

- `mailwyrm list --show-classification`
- `mailwyrm digest`

The original classifier output remains stored so corrections can be used later for evaluation.
