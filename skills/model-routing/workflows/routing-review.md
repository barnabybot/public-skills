# Routing review

`model-routing` owns routing checks and proposed catalogue revisions. Run
commands from `skills/model-routing/`:

```bash
python3 scripts/check.py --no-live --no-log
python3 scripts/preflight.py health --json
```

`check.py` validates `references/routing-catalog.json`, `SKILL.md` table
alignment, effort lists and cross-provider fallback chains.

## Live route evidence

Structural checks validate the catalogue and table. Live eligibility uses
`scripts/preflight.py preflight` (`--host t3` with `orchestrator_capabilities`,
`--host cmux` or `--host cli`), which checks enabled providers, exact model
IDs, option keys and active circuit breaker state.

## Propose a revision

Keep temporary provider trips separate from catalogue preference revisions:

1. Run structural checks and `scripts/preflight.py preflight` across your core categories.
2. Compare live host capabilities against `references/routing-catalog.json`. Record observation dates, tested efforts and limitations.
3. Write `$AGENT_NOTES/Ops/model-routing/YYYY-MM-DD Routing proposal.md` with evidence, expected effects and the diff against `references/routing-catalog.json` and `SKILL.md`.
4. Apply catalogue edits only after explicit user approval. Keep `SKILL.md` and `references/routing-catalog.json` aligned, then run `python3 scripts/check.py --no-live --no-log` and `python3 -m unittest discover -s scripts -p 'test_*.py'`.
