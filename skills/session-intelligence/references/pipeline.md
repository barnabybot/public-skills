# Session Intelligence pipeline reference

## Supported sources

`scripts/sources.py` reads local data only. Nothing leaves the machine unless
you invoke a model CLI during extraction or synthesis:

- **Claude Code** (`~/.claude/projects/*/*.jsonl`), skipping headless `sdk-*` calls.
- **Codex** (`~/.codex/sessions/**/rollout-*.jsonl`), skipping `codex_exec` and subagent children.
- **Grok** (`~/.grok/sessions/*/*/updates.jsonl`), skipping tab-naming helpers.
- **Muse** (`~/.local/share/muse/sessions/**/session.jsonl`), skipping subagents and headless `muse exec` runs.
- **Antigravity** (`~/.t3/userdata/providers/antigravity/*/antigravity-acp/brain/*/.system_generated/logs/transcript.jsonl` and `~/.gemini/antigravity/brain/`), reading `transcript_full.jsonl` for untruncated `<user_request>` blocks and skipping delegated T3 Code child threads.
- **Session notes** (`$AGENT_NOTES/Sessions/*.md`): enriches matched raw transcripts with `vault_note`, `vault_status` (`done`, `blocked`, `failed`), `## Goal`, and `## Outcome`, and ingests note-only records when no local transcript exists.
- **Scheduled job logs (optional)** (`$AGENT_NOTES/Cron/sessions/*.md`): compiles `data/cron-health.json` so synthesis avoids proposing duplicate scheduled jobs, and ingests failed runs when `cron` is enabled.

## Setup

```bash
SCRIPTS="<this-skill>/scripts"
AGENT_NOTES="${AGENT_NOTES:-$HOME/agent-notes}"
RUN="${RUN:-$AGENT_NOTES/Sessions/session-intelligence}"
mkdir -p "$RUN"
```

## Stage 1: Discover

```bash
python3 "$SCRIPTS/discover.py" --root "$RUN" --agents-vault "$AGENT_NOTES" --sources all --since-days 31 --min-turns 5
```

Add `--project-filter <substr>`, `--harness-filter <name>` or `--dry-run` as
needed. Discovery writes `data/work-list.jsonl`, `data/missing-full.json`,
`data/pilot.json`, `data/cron-health.json`, and compact digests under
`data/digests/<id>.txt`.

## Stage 2: Extract (loop until missing is zero)

Refresh `data/missing-full.json` before each round:

```bash
python3 "$SCRIPTS/build.py" assemble --root "$RUN"
```

- **Via `run_workflow`:**

```text
run_workflow(
  ScriptPath="$SCRIPTS/extract.workflow",
  Args={"scriptsDir": "<ABS_SCRIPTS>", "root": "<ABS_RUN>", "model": "flash"},
  Description="Extract findings from missing session digests"
)
```

- **Via portable CLI (`runner.py` across `agy`, `claude`, `codex`, `grok`, `muse`):**

```bash
python3 "$SCRIPTS/runner.py" extract --root "$RUN" --harness auto --concurrency 4
```

Re-run `build.py assemble` and repeat until `missing` is `0`.

## Stage 3: Synthesise and render the roadmap

- **Via `run_workflow`:** pass `ScriptPath="$SCRIPTS/synth.workflow"` with `Args={"scriptsDir": "<ABS_SCRIPTS>", "root": "<ABS_RUN>"}`.
- **Via portable CLI:** `python3 "$SCRIPTS/runner.py" synth --root "$RUN" --harness auto`.

Merge and render:

```bash
python3 "$SCRIPTS/build.py" merge  --root "$RUN" --synth-out "$RUN/data/synth-raw.json"
python3 "$SCRIPTS/build.py" render --root "$RUN"
```

## Stage 4: Behavioural portrait (optional, parallel)

- **Via `run_workflow`:** pass `ScriptPath="$SCRIPTS/life.workflow"` with `Args={"scriptsDir": "<ABS_SCRIPTS>", "root": "<ABS_RUN>"}`.
- **Via portable CLI:** `python3 "$SCRIPTS/runner.py" life --root "$RUN" --harness auto`.

Merge and render:

```bash
python3 "$SCRIPTS/build.py" merge-life  --root "$RUN" --synth-out "$RUN/data/life-raw.json"
python3 "$SCRIPTS/build.py" render-life --root "$RUN"
```

## Stage 5: Patterns (optional skill-improvement loop)

Compile execution traces into a persistent pattern wiki under
`WIKI=$AGENT_NOTES/Ops/skill-patterns` before patching one skill:

```bash
python3 "$SCRIPTS/patterns.py" sample   --from-run "$RUN" --out "$TRACES" --seed 1
python3 "$SCRIPTS/patterns.py" maintain --wiki "$WIKI" --traces "$TRACES" --skill <SKILL.md> --iteration <label> --harness auto
python3 "$SCRIPTS/patterns.py" propose  --wiki "$WIKI" --traces "$TRACES" --skill <SKILL.md> --out "$WIKI/proposals/<label>" --iteration <label> --harness auto
python3 "$SCRIPTS/patterns.py" verify   --wiki "$WIKI"
```

For deterministic tooling-skill friction scanning and read-only replay:

```bash
python3 "$SCRIPTS/friction.py" scan    --skill cmux --sources all --out "$SCAN"
python3 "$SCRIPTS/friction.py" holdout --hits "$SCAN/hits.jsonl" --n 8 --seed 1 --out holdout.json
python3 "$SCRIPTS/friction.py" traces  --skill cmux --scan "$SCAN" --exclude holdout.json --run "$RUN" --out "$TRACES"
python3 "$SCRIPTS/friction.py" replay  --holdout holdout.json --skill cmux --skill-file <SKILL.md> --harness auto --out "$ARM"
python3 "$SCRIPTS/friction.py" score   --results "$ARM/results.json"
```

## Outputs (under `$RUN/data` and `$RUN/app`)

| File | What |
| --- | --- |
| `data/work-list.jsonl` | Ranked candidate sessions across runtimes and `$AGENT_NOTES`, with digest paths and resume commands |
| `data/cron-health.json` | Optional per-job scheduled run and failure summary for the window |
| `data/conversations.jsonl` | One verified structured record per session |
| `data/observations.jsonl` | Flattened evidence stream (`friction`, `toil`, `preference`, `automation`), each with `evidence_verified` |
| `data/synthesis.json` | Roadmap, runtime and domain profiles, skill backlog, new skills and jobs, `agents_md_rules` |
| `data/life.json` | Behavioural portrait (`one_liner`, `portrait`, `patterns`, `tensions`, runtimes) |
| `app/index.html`, `app/life.html` | Self-contained editorial HTML apps with period filtering and clickable source sessions |
