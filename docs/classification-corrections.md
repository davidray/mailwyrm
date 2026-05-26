# Classification Corrections

Classification corrections are local user feedback for improving Mailwyrm's classifier before any Gmail-writing automation exists.

Corrections do not mutate Gmail.

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
