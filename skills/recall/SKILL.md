---
name: recall
version: 1.1.0
description: >-
  Load session memory. Use for recall, prime context, yesterday, last week, session history or topic memory.
argument-hint: [yesterday|today|last week|this week|TOPIC|graph DATE_EXPR]
allowed-tools: Read, Glob, Grep, Bash(python3:*), Bash(rg:*), Bash(grep:*), Bash(qmd collection list), mcp__qmd__query, mcp__qmd__get, mcp__qmd__multi_get
---

# Recall

Three modes: temporal (a date-based session timeline), topic (a search across
your notes), and graph (an interactive visualisation of session-to-file
relationships). Every recall ends with the **One Thing** - one concrete,
highest-leverage next action synthesised from the results.

## What it reads

Read session notes first when they exist under `$AGENT_NOTES/Sessions/`.
They can cover every recorded agent. Reconcile records by frontmatter
`session_id`, retain hand-written decisions and outcomes, and open native
transcripts for missing detail. Without session notes, use the raw transcripts:

- Claude Code: `~/.claude/projects/*/*.jsonl`
- Codex CLI: `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`

Those are the default locations each tool ships with. Pass `--no-codex` to
restrict the scan to Claude Code.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/` |

The native timeline works without session notes or a search index. QMD users
discover which collection indexes their notes; collection names are local
configuration. File search remains available when a search index is absent.

## Dependencies

| Mode | Needs |
|---|---|
| Temporal | `python3`. Nothing else. |
| Graph | `python3`, plus `networkx` and `pyvis` (`pip install networkx pyvis`). |
| Topic | A search tool over your notes. See "Topic recall" below. |

## Intake

One panel, before `workflows/recall.md` is read, and before any script or query
runs. An argument after `/recall` settles the panel and it is skipped; a bare
`/recall` asks. Say what you read in the line above the panel.

**Mode** - What kind of recall?
- Temporal - session notes for a date window, with native transcripts as fallback
- Topic - a search across your notes for a subject you give after the panel
- Graph - the interactive HTML graph of sessions and the files they touched
- Both - search for the subject, then filter matching sessions by date
- settled by: a date phrase (Temporal); "graph" first (Graph); a subject noun (Topic); a subject with a date phrase (Both)

**Window** - Which dates?
- Yesterday - one day back
- Today - the current day so far
- Last week - the previous seven days
- Named - "this week", a date, a weekday or "N days ago", given after the panel
- settled by: a date expression in the request; Topic (none)

**Source** - Which native transcripts, when expanding a note or using the fallback?
- Both - Claude Code and Codex rows, marked CC and CX (the default)
- Claude Code - `--no-codex`
- settled by: `--no-codex` (Claude Code); session-note discovery alone (all recorded agents)

Text fields, one message after the panel: the subject where Mode is Topic or
Both, and the date expression where Window is Named.

## What it does

- **Temporal queries** ("yesterday", "last week", "what was I doing"): reads dated
  session notes. Where notes are absent or incomplete, the native timeline
  covers Claude Code and Codex. Expand a selected session for missing detail.
- **Topic queries** ("authentication", "the chart rewrite"): searches across
  your notes for a subject.
- **Graph queries** ("graph yesterday", "graph last week"): generates an
  interactive HTML graph showing sessions as nodes connected to the files they
  touched.
- **One Thing synthesis**: after presenting results, names the single most
  impactful next action, based on what has momentum, what is blocked, and what
  is closest to done.

## Workflow & references

- `workflows/recall.md` - routing logic, step-by-step recall and the **Discovery for another skill** contract.
- `references/usage.md` - invocation examples, topic recall (QMD MCP or file search) and script paths (`scripts/recall-day.py`, `scripts/session-graph.py`, `scripts/extract-sessions.py`).
