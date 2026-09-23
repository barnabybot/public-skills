# Intake panels

How a skill asks for what it needs before it starts. One panel, at the outset,
every option explained. The reference render is the `frontend-slides` plugin's
Phase 1: four tabs, one submit, each option with a line on what it gives.

## The contract

1. **Panel first.** `## Intake` is the first section after the title. Present
   it before reading any other file. The inputs are the request and the section
   itself.
2. **One panel.** Every question whose answer does not depend on another answer
   goes in the same panel. At most four questions, at most four options each.
   A fifth question or option means the skill has two jobs, or the question
   belongs downstream of the panel.
3. **Every option explains itself.** `label — what choosing it gives`. A bare
   label fails validation.
4. **The request settles what it can.** Each question carries a `settled by:`
   line. When the request settles a question, drop it from the panel and state
   the reading in the line above the panel: "Reading Content as written already;
   say otherwise and I'll ask." An inference the user cannot see costs a round
   trip to unwind.
5. **Text fields follow, together.** Names, sentences and paths cannot be
   options. List every text field in one message after the panel. Never one per
   turn.
6. **A dependent question waits one panel.** Mark it `after: <Header>`. Prefer
   a redesign that removes the dependency over a second panel. A question that
   is asked only in the slot another question frees carries `slot of: <Header>`
   and sits outside the cap of four.
7. **Confirm-before-write is a gate.** It stays where the write happens and is
   never counted as intake.

## Rendering

| Host | Mechanism |
|---|---|
| Claude Code | One `AskUserQuestion` call carrying every open question. Header 12 characters or fewer. A recommended option goes first with "(Recommended)" on the label. |
| Codex | `request_user_input`, the same panel. Requires `default_mode_request_user_input = true` under `[features]` in `~/.codex/config.toml`; re-check after Codex updates, which have dropped it before. A host without it falls back to the text form. |
| Text form | One message. Questions numbered, options lettered, each with its description, the recommended option marked. Reply as `1A 2C 3B`. |
| Headless (cron) | No panel. The skill's `fallback:` field or its headless workflow names the defaults. |

## Authoring form

The block below is the shape. Headers are bold, options are dashes, the
description follows a spaced em dash (a spaced hyphen also passes).
The panel names no file. When the preamble pointed at this contract, both hosts
read the file before showing the panel, which breaks rule 1.

```markdown
## Intake

One panel, before any other read. Skip what the request settles; say what you read.

**Purpose** — What is this deck for?
- Pitch — persuade an audience to back a proposal, deal or investment
- Teaching — walk through a method or material step by step
- Talk — live keynote-style delivery to a room
- Internal — team or client-internal review
- settled by: a named occasion or audience

**Content** — What do you have?
- Written — the material exists; paste it or name the file
- Rough notes — bullets or an outline to shape
- Topic only — a subject and audience; the outline comes first
- settled by: an attached file (Written), a bullet list (Rough notes), one line (Topic only)

Text fields, one message after the panel: none.
```

## Registry-backed options

An option set that mirrors a registry (a brand axis that mirrors
`brands/registry.json`) is still written inline, with a `mirror of:`
line naming the source. Keeping the two in step is a review-checklist item on
any change to the registry. The panel never waits on a file read at run time.

## Routers

A family router with more than four children asks in two steps: the job bucket
(four or fewer) plus the one axis every child shares, then the chosen child's own
panel. A direct slash invocation of a child skips the router step.

## Validation

`scripts/validate.sh` checks every `## Intake` section and fails on: more than
four questions in the panel (`slot of:` questions excluded); fewer than two or
more than four options on a question; an option without a description. A skill
whose body names `AskUserQuestion` or `request_user_input` and carries no
`## Intake` section warns.
