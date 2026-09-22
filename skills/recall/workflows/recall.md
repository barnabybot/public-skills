# Recall workflow

Load context from session memory. Temporal queries read the native JSONL
transcripts; topic queries search your notes.

`SKILL_DIR` below is the directory this skill is installed in - typically
`~/.claude/skills/recall`.

## Step 1: classify the query

Parse the user's input after `/recall` and classify it:

- **Graph** - starts with "graph": "graph last week", "graph yesterday". → Step 2C
- **Temporal** - mentions time: "yesterday", "today", "last week", "this week",
  a date, "what was I doing", "session history". → Step 2A
- **Topic** - mentions a subject: "authentication", "the chart rewrite". → Step 2B
- **Both** - time plus subject: "what did I do with the parser yesterday". →
  Step 2A first, then scan the results for the topic.

## Step 2A: temporal recall (JSONL timeline)

```bash
python3 "$SKILL_DIR/scripts/recall-day.py" list DATE_EXPR --all-projects
```

Replace `DATE_EXPR` with the parsed date expression. Supported:

- `yesterday`, `today`
- `YYYY-MM-DD`
- `last monday` .. `last sunday`
- `this week`, `last week`
- `N days ago`, `last N days`

Options:

- `--min-msgs N` - filter noise (default 3, Claude rows only)
- `--all-projects` - scan every project
- `--no-codex` - exclude Codex CLI transcripts (they are included by default)

The table covers both harnesses, and the `Src` column marks each row `CC` or
`CX`. Codex `Msgs` counts real human turns, so CX numbers read lower than CC,
which also counts tool-result messages. Use the `Size` column for a fairer
cross-harness comparison of magnitude.

Present the table. If the user picks a session to expand:

```bash
python3 "$SKILL_DIR/scripts/recall-day.py" expand SESSION_ID --all-projects
```

## Step 2B: topic recall

Two paths. Use the first one available and say in the reply which you used.

**With a semantic search tool** (QMD MCP, or equivalent). Combine a lexical and
a vector sub-query.

1. **Expand the query into variants.** Generate two or three alternative
   phrasings someone might use for the same topic.
2. **Run the search:**

   ```json
   {
     "searches": [
       {"type": "lex", "query": "exact keywords from the user's query"},
       {"type": "vec", "query": "natural-language description of what they want"}
     ],
     "limit": 10,
     "minScore": 0.3
   }
   ```

   For a more nuanced topic, add a hypothetical-document sub-query:

   ```json
   {"type": "hyde", "query": "50-100 word passage describing what the answer looks like"}
   ```

3. **Fetch the top results** for the most relevant documents.

**Without one**, grep the notes root and any other folder the user names:

```bash
grep -rilE 'term1|term2|term3' "${AGENT_NOTES:-$HOME/agent-notes}/Sessions/"
```

Read the matches and rank them by recency and by how central the term is. Say
that this was a keyword search, because it finds the word rather than the
subject.

## Step 2C: graph visualisation

Strip the "graph" prefix from the query to get the date expression:

```bash
python3 "$SKILL_DIR/scripts/session-graph.py" DATE_EXPR --all-projects
```

Options:

- `--min-files N` - only show sessions touching N or more files (default 2)
- `--min-msgs N` - filter noise (default 3)
- `-o PATH` - output path (default `/tmp/session-graph.html`)
- `--no-open` - do not open a browser

Needs `networkx` and `pyvis`. Where the import fails, say so and offer the
temporal table instead.

## Step 3: present a structured summary

**Temporal:** present the session table and offer to expand any session.

**Topic:** organise the results by relevance:

- what was worked on related to this topic
- key dates and decisions
- the current status, or the next steps

Keep this concise. It is context loading, and not a full report.

## Step 4: synthesise the One Thing

After presenting the results, name the single highest-leverage next action.

How to pick it:

1. Look at what has momentum - sessions with recent activity, things mid-flow.
2. Look at what is blocked - removing a blocker unlocks downstream work.
3. Look at what is closest to done. Finishing beats starting.
4. Weigh urgency signals: deadlines in session titles, `blocked` status,
   time-sensitive content.

**Format:** a bold line at the end of the results.

> **One Thing: [specific, concrete action]**

Good examples:

- **One Thing: finish the parser outline - sections 3 to 5 are drafted and it needs the closing section**
- **One Thing: unblock the deploy - the DNS config is the only remaining blocker**

Too generic to be useful:

- "Continue working on the parser"
- "Pick up where you left off"

Where the results carry too little signal, skip it and ask "What would you like
to work on?" instead.

## Fallback: no results found

```
No results found for "QUERY". Try:
- different search terms
- broader keywords, or a different date range
- --min-msgs 1 to include short sessions
```
