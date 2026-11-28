---
name: session-intelligence
version: 1.0.0
attribution: "Forked and adapted from Artem Zhutov's session-intelligence skill"
description: >-
  Mine multi-runtime agent traces and agent session notes into an interactive
  automation roadmap and behavioural portrait, evidence-verified. Use for
  /session-intelligence, "analyse my sessions", "what patterns do I repeat",
  "how do I work" or "mine my history".
fallback: >-
  If python3 is unavailable or no local trace roots and $AGENT_NOTES folder
  exist, report the missing inputs and stop rather than building a roadmap from
  empty evidence.
---

# Session Intelligence

Turn local agent session traces and `$AGENT_NOTES` session notes into two
evidence-backed self-contained HTML apps (with period filtering and clickable
source sessions):

- **Roadmap app** (`app/index.html`) with ranked automation opportunities,
  skill backlog, `AGENTS.md` rule candidates, optional scheduled-job health,
  and clickable source sessions.
- **Behavioural portrait** (`app/life.html`) capturing repeating working
  patterns across runtimes in verbatim user quotes.

The product is the insight. The HTML is how you explore it.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/`, optional cron logs in `Cron/sessions/` |
| `SESSION_FONTS_DIR` | *(unset)* | Optional local font directory to embed; uses system editorial stack when unset |

## Intake

One panel, before any script runs or any trace is read. Skip what the request
settles; say what you read in the line above the panel.

**Window** - How far back?
- 31 days - `--since-days 31` (the default)
- 90 days - a quarter of sessions
- All - every trace and session note on disk (`--since-days 0`)
- settled by: a number of days in the request

**Sources** - Which session sources?
- All sources - Claude Code, Codex, Grok, Muse, Antigravity, session notes and scheduled-job failures (the default)
- Local transcripts - raw JSONL transcripts across installed runtimes without vault-only notes
- Notes only - `Sessions/*.md` notes and optional `Cron/sessions/*.md` failures
- One runtime - filter with `--sources <name>` or `--harness-filter`
- settled by: a named runtime or source in the request

**Scope** - Which projects?
- All projects - every project across the selected sources
- One project - `--project-filter`, named after the panel
- settled by: a project name or path in the request (One project)

**Output** - What is built?
- Roadmap - `app/index.html`, the ranked automation opportunities (the default)
- Roadmap and portrait - the roadmap plus `app/life.html`
- Portrait only - `app/life.html` alone
- Patterns - the pattern-wiki loop on one skill and one atomic patch
- settled by: "how do I work" or "what patterns do I repeat" (Roadmap and portrait); a skill name (Patterns)

## Quickstart

Run from this skill directory (full 5-stage pipeline, workflow arguments,
pattern-wiki loop and output schemas live in [pipeline.md](references/pipeline.md)):

```bash
RUN="${RUN:-${AGENT_NOTES:-$HOME/agent-notes}/Sessions/session-intelligence}"
python3 scripts/discover.py --root "$RUN" --sources all --since-days 31 --min-turns 5
python3 scripts/build.py assemble --root "$RUN"
python3 scripts/runner.py extract --root "$RUN" --harness auto --concurrency 4
python3 scripts/runner.py synth   --root "$RUN" --harness auto
python3 scripts/build.py merge    --root "$RUN" --synth-out "$RUN/data/synth-raw.json"
python3 scripts/build.py render   --root "$RUN"
```

In hosts exposing `run_workflow`, run `scripts/extract.workflow`,
`scripts/synth.workflow` and `scripts/life.workflow` for inline zero-tool-call
execution.

## Hard rules and error recovery

1. **Deterministic quote verification.** `build.py assemble` checks every quote
   against that session's digest and sets `evidence_verified`. Drop findings
   without verbatim quotes.
2. **Loop until missing is zero.** Durable per-session outputs under
   `data/runs/conv-<id>.json` let subsequent rounds recover stragglers cleanly.
3. **Zero-tool-call workflows.** `extract.workflow`, `synth.workflow` and
   `life.workflow` pack compact payloads inline in Python so background agents
   never block on out-of-workspace reads.
4. **No traces found.** Stop and report which source directories were empty;
   never fabricate roadmap findings from zero sessions.
