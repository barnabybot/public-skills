# Agent instructions

This is a working instruction file for coding agents. Put it at the root of a
project as `AGENTS.md`, and symlink `CLAUDE.md` to it so Claude Code and Codex
read the same file. There is then one canon and no second copy to keep in step.

It is written to be edited. The rules below are general. The parts that describe
where files go and how sessions are logged are conventions, so change them to
match your own layout.

## 1. Think before coding or acting

**Do not assume. Do not hide confusion. Surface tradeoffs.**

Before implementing or taking action:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Do not pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what is confusing. Ask.
- When a request matches a skill, read that skill's `SKILL.md` first, before
  asking anything. Its `## Intake` section is then the first thing you ask, as
  one panel, before any other file is read. Use the host's own question tool
  where it has one: `AskUserQuestion` in Claude Code, `request_user_input` in
  Codex. On a host with neither, send one message with the questions numbered
  and every option carrying its description. Never compose your own questions in
  place of the skill's panel, and never auto-configure past it.

## 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility or configurability that was not requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

**The test:** would a senior engineer say this is overcomplicated? If yes,
simplify.

## 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Do not improve adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match existing style, even where you would do it differently.
- If you find unrelated dead code, mention it. Do not delete it.

When your changes create orphans:

- Remove imports, variables and functions that YOUR changes made unused.
- Do not remove pre-existing dead code unless asked.

**The test:** every changed line traces directly to the user's request.

## 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Turn imperative tasks into verifiable goals:

| Instead of...    | Transform to...                                       |
| ---------------- | ----------------------------------------------------- |
| "Add validation" | "Write tests for invalid inputs, then make them pass" |
| "Fix the bug"    | "Write a test that reproduces it, then make it pass"  |
| "Refactor X"     | "Ensure tests pass before and after"                  |

For multi-step tasks, state a brief plan:

```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## 5. Thin-slice gate

Before any action that repeats across more than one item (fan-out), or writes to
a live, shared, public, or external surface (irreversibility), STOP. Produce one
representative example - one card, one page, one record, one file - show it,
usually as HTML, and wait for an explicit "go".

Must-gate examples: bulk-editing N posts or files, writing a visual
presentation, replacing a live template, running a migration or a sweep.

**The test:** if a mistake here would repeat N times, or land somewhere you
cannot quietly undo, ship one slice and wait.

## Writing voice

This applies to anything the user reads: articles, emails, code comments, hook
output, notes, commit messages, chat replies. The same taste threshold covers
all of it. The full canon is in the `editorial-review` skill in this repository.

Write in Simplified Technical English (ASD-STE100). Use a neutral, academic and
hyper-concise technical tone.

**Banned vocabulary** (strike on the first draft): delve, landscape (as
metaphor), leverage (as verb), tapestry, weave, navigate (as metaphor), robust,
comprehensive, multifaceted, underscores, nuanced, pivotal, paramount,
fostering, realm, harness, seamlessly, crucial, furthermore, moreover,
additionally, showcase, intricate, vibrant, interplay.

**Banned phrases:** "here's the thing", "the bottom line", "make no mistake",
"in today's fast-paced world", "it is important to note", "it could be argued".

**Banned structures.** These are the loudest tell, and the easiest to miss in
your own draft.

- **Negation-contrast.** Every shape is flagged, with no load-bearing exception:
  - `X, not Y`
  - `It's not X, it's Y` and `It's not just X, it's Y`
  - **The fix:** drop the negation half. The affirmative usually stands alone.
- **Phantom contrast**, where the negated half names a claim nobody made, is
  rhetorical filler and is always cut. If you catch yourself justifying the
  construction as "earned" or "load-bearing", reject the justification and
  rewrite.
- **Fence-sitting** ("on the one hand... on the other"). Take a side.
- **Tricolon drumbeat.** Vary list lengths.
- **Metronomic paragraphs.** Vary rhythm.

**Punctuation**

- No unspaced em dashes inside sentences. Use commas, periods, colons, or a
  spaced " - ".
- British English (organise, utilise, behaviour, prioritise, analyse, programme,
  tokenise).

**Write-time discipline, and not a review pass.** Apply this at the sentence as
you draft. Every time you reach for "X, not Y" or twin parallel-verb sentences,
stop and write the affirmative half alone. A regex catches words; the structural
tics need a sentence-level read-aloud while you write.

## File placement

The point of this section is that every kind of output has one known home, so
the next session inherits a path rather than a guess. Set the paths to your own
layout and keep the shape.

- Substantive output goes to the matching project folder, and never to the home
  directory.
- A skill's own engineering evidence - renders, probes, measurements, extraction
  records - goes to one operations folder per skill.
- Session history, pickup prompts and handoff prompts go to the agent-notes
  root. The skills in this repository read `$AGENT_NOTES`, which defaults to
  `~/agent-notes`:
  - session notes: `$AGENT_NOTES/Sessions/`
  - handoffs and pickup prompts: `$AGENT_NOTES/Sessions/Handoffs/`
- Throwaway temp files go to a dated scratch folder, one per day, outside every
  vault and repository, so nothing syncs or commits from it. Anything older than
  seven days may be deleted without asking. Where the host gives the session its
  own scratchpad directory, use that instead.
- The Desktop stays empty. Nothing lands there: no scratch, no captures, no test
  renders, no session history, no handoff prompts. A file on the Desktop is a
  leaked write.
- Never put working files in a skills repository. That repository holds skills.
  Everything a skill *produces* goes to the matching project folder.
- A discovery about a repository's own tooling, environment or failure modes
  goes into that repository's own knowledge store, because that is what the next
  agent opening the repository will read. The session note records that it
  happened.

## Output naming

Name every generated artefact with the date it was built: `YYYY-MM-DD
Title.ext`. Rebuild it and it takes today's date, so successive builds sit side
by side and the current one is unambiguous.

- **Applies to every output format**: `.pdf`, `.html`, `.xlsx`, `.pptx`,
  `.docx`. Plan documents, dossiers, decks, rendered reports, and any workbook a
  builder writes.
- **Raw evidence keeps the date it arrived with.** A data extract, a supplied
  template, a third-party PDF, a screenshot, a downloaded source: leave the
  filename alone. Renaming raw data destroys the record of when it was pulled
  and breaks the tie between a figure and its source.
- **The builder composes the dated name.** A script with a fixed output path
  overwrites its own history on every run. Build the filename from the build
  date so each run is kept, and a rebuild never silently replaces the artefact
  someone is reading.

## Session-note discipline

Every non-trivial session needs a note at `$AGENT_NOTES/Sessions/YYYY-MM-DD
<slug>.md`, using the local date and a three-to-five-word lowercase slug. Set
`agent:` to what you actually are, because the dashboard groups on it.

**Write it at the start**, once the user has stated a goal. A crash or a closed
terminal loses a note that was only ever going to be written at the end.

Non-trivial means debugging, refactor, implementation, audit, research or
planning; a session past about three prompts; or any file write. Skip a one-line
answer, a single-shot lookup, or an explicit "no need to log this". Skip rules
win. Update today's existing note for the same goal rather than opening a second
one.

At session end set `status:`, add `ended:`, and fill `## Outcome`. `status:` is
a closed vocabulary of six values: `queued`, `in-progress`, `review`, `done`,
`blocked` and `failed`. Lowercase and hyphenated, never quoted. `done` means off
the board, and does not always mean the work shipped; say which in `## Outcome`.
Never normalise `failed` to `done` - it carries information `done` destroys.

## Secrets and credentials

Keep API keys and passwords in a password manager with a command-line interface,
and read them from there at the moment of use. Never paste a secret into a
prompt, a note, a commit or a handoff file.

Before writing any durable artefact - a handoff, a session note, a committed
file - scan it for keys, tokens, passwords, OAuth client secrets, private keys
and personal data. Assume anything written to disk is durable and shareable.

## Commit discipline

- One logical change per commit.
- Never skip hooks with `--no-verify` unless the user explicitly asks.
- Stage specific files, never a broad `git add .` or `git add -A`.
- Use a short imperative subject under 70 characters, with a body when the
  reason is not obvious.
- Ask before every push to a repository that publishes on push.

## Cross-tool awareness

Sessions from different agent harnesses land in the same flat
`$AGENT_NOTES/Sessions/` folder, separated by the `agent:` frontmatter field.
When the user refers to yesterday's session or an earlier workspace, read that
note before assuming context.

**"Handoff" and "handover" mean spawn a new workspace.** They do not mean a
clipboard, a file path, or a question about whether to spawn. Write the prompt
under `$AGENT_NOTES/Sessions/Handoffs/` with a dated filename, then spawn it and
report the workspace name. The `handoff` and `cmux` skills in this repository do
this. Produce a clipboard handoff only on an explicit request to copy, and park
only on an explicit `park`.
