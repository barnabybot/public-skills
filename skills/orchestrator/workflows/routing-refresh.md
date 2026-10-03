# Routing refresh

A scheduled check of the routing table against Artificial Analysis (AA). The script ranks the models in your metadata for each category. The orchestrator seat turns a changed ranking into a proposal. The table changes only after the user rules.

## Weekly run

Run it weekly from any scheduler (cron, launchd, a CI timer). From the skill directory:

```bash
AGENT_NOTES="$HOME/agent-notes" python3 scripts/aa_refresh.py --quiet
```

A crontab line for Monday 07:00:

```
0 7 * * 1  cd <path-to>/skills/orchestrator && python3 scripts/aa_refresh.py --quiet
```

The script reads the model records embedded in one AA model page and keeps the models in `references/routing-metadata.yaml` that carry `aa_release`. For each category in the `aa` block it:

1. Finds the efficient settings: each model-and-effort pair that no other pair beats on both score and cost.
2. Steps up from the cheapest setting while each extra point of the category measure costs no more than the class limit in `cost_per_point`. That stop is the knee and becomes the pick.
3. Repeats steps 1 and 2 on the other providers for the backup.

It writes `$AGENT_NOTES/Ops/orchestrator/aa/YYYY-MM-DD AA routing refresh.md` and a JSON snapshot beside it. `--out DIR` writes elsewhere; `--no-write` writes nothing.

## Output contract

| Exit | Meaning | stdout with `--quiet` |
|---|---|---|
| 0 | Picks and the successor list match the last snapshot | Empty |
| 4 | A pick changed, or AA lists a new successor to one of your models | The report, with the changed lines |
| 1 | Fetch or parse failed: the AA page format may have changed | `[ERROR: …]` |

A scheduler that mails or forwards any output therefore stays silent until there is something to read. Without `--quiet` the report prints on every run.

## Coverage

A model with no `aa_release` is left out of the ranking. A category where no model is ranked reports `none` for the pick, and a category where only one provider is ranked reports `none` for the backup. The shipped placeholder fleet ranks only the `provider_a` models; add the AA release slug of each `provider_b` model to rank the backup column. The slug is the last part of the model's URL on artificialanalysis.ai.

## On an alert

The orchestrator seat runs this list. It does not edit the table.

1. Read the report. For each successor, confirm that the CLI offers it: `python3 scripts/check.py`, or one short prompt with the new ID. A subscription can lag the API by weeks.
2. Cross-check the categories that AA does not measure, on Arena (arena.ai), by hand:
   - Visual: WebDev board.
   - Orchestrator: the agent work board.
   - Writing: your own blind test decides. Arena Creative Writing is context only.
   Mark any model with fewer than about 3,000 votes as low-n.
3. For classification, run a sample test: about 20 notes that the user has already classified, two or three candidate settings from the report, and the cheapest setting that matches at least 19 labels.
4. Write the proposal with `workflows/routing-review.md`, step 4 onwards. Quote the report for each measured row.

## Limits

- AA cost is API dollars per Intelligence Index task. Seats that run on subscriptions see it as token burn within one provider. It is a weak guide between providers.
- The coding and systems measure is Terminal-Bench 4.0, because the page embeds no Coding Agent Index figure.
- A provider whose allowance cannot be read can carry `inferred: false` in its metadata entry, and it is never ranked. `aa_exclude: [presented]` on a model keeps it out of the presented class.
- The script proposes. A ruling from the user changes the table.
