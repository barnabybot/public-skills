# Catalogue

Run the validator for every folder under `skills/` with a `SKILL.md`. The
current catalogue contains ten skills, including `model-routing` and `hygiene`.

## Sub-features

- `catalogue-validate-all`. Record each skill's result and the combined exit.

## How to get to it (user POV)

From the repository root, run the local helper before publishing downloads.
The helper resolves the repository root from its own location and invokes
`skills/skill-manager/scripts/validate.sh` for every catalogue entry.

Source: [validate-all](../scripts/validate-all), lines 3-29, and
[the catalogue](../../../../README.md), lines 91-101.

## Live recipe

Use [Launch and Doctor](../SKILL.md), then the Drive command there. Set
`SHOT_OUT` to a fresh absolute evidence directory for this drive.

Require process exit 0. Compare `summary.txt` against `skills/*/SKILL.md` so
every source entry has exactly one `ok <name>`. Require all per-skill `.exit`
files and `exit.txt` to contain `0`. Keep every transcript, including warnings.

## Gotchas

- WARNs, such as a long `SKILL.md` or advisory CLI findings, allow exit 0.
- FAILs block the catalogue. Keep the failure evidence and run Doctor again.
- This checks the automatable structural subset of the review checklist.
