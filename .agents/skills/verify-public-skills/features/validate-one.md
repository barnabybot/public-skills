# Validate one

## Sub-features

- `validate-recall`. Validate `skills/recall` as the representative skill.

## How to get to it (user POV)

Use `/skill-manager` Review, or run its validator directly with a skill
directory as the argument. Structural failures return a nonzero exit. Warnings
advise and the output lists the checks that still need human review.

Source: [validate.sh](../../../../skills/skill-manager/scripts/validate.sh),
lines 4-8, 43-125.

## Live recipe

Use [Launch and Doctor](../SKILL.md) in a fresh CLI session, then run:

```bash
bash skills/skill-manager/scripts/validate.sh skills/recall
```

Keep the command and transcript. Require process exit 0 and a final result
with `0 failed`.

## Gotchas

- Pass the skill directory, such as `skills/recall`.
- An invalid directory returns exit 2 with usage guidance.
