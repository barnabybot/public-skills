# Recall usage, topic search and scripts

Invocation examples, QMD and file-search topic recall, workflow handoff contract and script constants.

## Usage

```
/recall yesterday
/recall last week
/recall 2026-09-22
/recall authentication work
/recall graph last week
```

## Topic recall

Topic mode needs a search tool over your notes, and which one is yours to
choose. The `allowed-tools` header names [QMD](https://github.com/qmd-sh/qmd)
MCP tools (`mcp__qmd__query`, `mcp__qmd__get`, `mcp__qmd__multi_get`), which
combine lexical, vector and hypothetical-document sub-queries and rerank the
results. That is the strongest option where you have it.

Scope past-work queries to the collection that indexes your session notes.
Where an index is unavailable, use file search over `$AGENT_NOTES/Sessions/`
and any other folder the user names. If the notes directory is absent, use
the native timeline and state its agent coverage. Report the route used.

`workflows/recall.md` carries the query shapes for both.

## Workflow

See `workflows/recall.md` for the routing logic and the step-by-step process.

When another skill requests session discovery, use that workflow's
**Discovery for another skill** contract. Reuse its supplied scope and return
source records to the caller. Retrospective owns the later evaluation.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/recall-day.py` | The temporal timeline. `list <date-expr>` prints the session table; `expand <session-id>` prints one conversation. |
| `scripts/session-graph.py` | The interactive HTML graph of sessions and the files they touched. |
| `scripts/extract-sessions.py` | Exports transcripts to Markdown, for indexing sessions in a search tool. |

Each script hoists its transcript paths into module-level constants
(`CLAUDE_PROJECTS`, `CODEX_SESSIONS`, `CODEX_ARCHIVED`). Edit those where your
harness writes somewhere else.
