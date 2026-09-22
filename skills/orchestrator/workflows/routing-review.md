# Routing review

The orchestrator owns routing checks, route-log summaries and proposed preference changes.
Run commands from the skill directory.

```bash
python3 scripts/check.py --no-live --no-log  # structural checks
python3 scripts/check.py                    # add installed model and capacity checks
python3 scripts/routelog.py --since YYYY-MM-DD
```

`check.py` validates every table row, model reference, effort and cross-provider backup. Live checks confirm installed model IDs where the CLI exposes them; Claude IDs receive a shape check and need a spawn to confirm. Capacity failures are reported as unread. Check and log commands append evidence under `Agents/Ops/orchestrator/`; use `--no-log` for validation runs.

## Propose a revision

Use this workflow when asked to refresh preferences or assess a new model. Keep temporary capacity overrides separate from preference changes.

1. Run the checks and read dispatch outcomes since the last review.
2. Read current primary model documentation and relevant benchmark results. Record dates, tested effort and limitations. Existing evidence is in `references/routing-metadata.yaml`. Where a model refuses briefs in a particular vocabulary, keep your own rewrite table beside that file.
3. Compare candidate changes with the user's recorded rulings and actual route outcomes. State which choices are measured, inherited practice or user rulings.
4. Write `YYYY-MM-DD Routing proposal.md` somewhere durable, with evidence, expected effects and a diff against the table in `SKILL.md`. Include any needed metadata changes.
5. Apply preference changes only after the user approves the proposal. Every table edit must carry matching `basis` and `evidence` updates in `references/routing-metadata.yaml`; keep the tier name aligned and record the revision date and approval source. Run structural checks, resolver tests and cmux spawn fixtures before publication.

Structural validation does not test live launches, output quality or available subscription capacity. Report those limits with the result.
