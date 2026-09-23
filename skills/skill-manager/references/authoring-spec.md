# Authoring spec — structure, frontmatter, description, budget

## Skill structure

Skills are self-contained. Everything the skill needs lives inside its folder.

```
my-skill/
├── SKILL.md              # router — under 100 lines
├── references/           # detail loaded on-demand
├── workflows/            # step-by-step procedures
├── scripts/              # deterministic helpers (Python by default)
├── templates/            # templates INSIDE the skill
└── docs/                 # troubleshooting, edge cases
```

## Frontmatter fields

Required:

```yaml
name: my-skill          # kebab-case, ≤64 chars
description: |          # see Description below
```

Required for children of a skill family (see `naming-conventions.md`):

```yaml
parent: research        # the family router that owns this skill
```

Optional:

```yaml
origin: local | vendor
version: X.Y.Z
allowed-tools: [...]
user-invocable: true
fallback: "..."         # what to do if the skill's scripts cannot run
```

## Description field

The `description:` in frontmatter is the ONLY text the agent reads when deciding
whether to load a skill. It must teach both WHAT and WHEN.

- ≤1024 characters
- Third person ("Applies..." not "I apply...")
- Name concrete user phrases, file types, or task shapes as triggers
- Include the slash-command name in the description

### User-facing skills

Two-sentence shape: capability statement, then "Use when [triggers]".

```
description: |
  Apply data-story judgement to charts and HTML outputs.
  Use for /charts, or when the user asks to build, review, or choose
  charts: "data visualisation", "chart", "dashboard", or "plot this".
```

### Headless / cron skills

Headless skills have no user trigger. Use the shape: capability statement, then
"Triggered by [schedule/event]. Produces [output]."

```
description: |
  Collect yesterday's build failures and write a triage note. Triggered
  by the 06:00 UTC cron. Produces notes/build-triage-<date>.md.
```

## SKILL.md length budget

| Lines | Verdict |
|---|---|
| <100 | Target |
| 100-200 | Warn — becoming a reference doc |
| >200 | Split into references/, docs/, or workflows/ |

Content used <20% of the time or exceeding 50 lines belongs in a sibling file.
The base SKILL.md stays as a router.

### Parent routers

Family routers (a parent skill that routes to several children) are justified
composite routers. They may exceed 100 lines when they carry an operator console,
lifecycle diagram, routing table, role library, and context system. Even
parent routers should stay under 200 lines — push detail into CLAUDE.md or
AGENTS.md. Parent routing tables use a standard column schema:

```markdown
| User cue | Skill | Notes |
```

Where "Skill" is always the slash command (`/research-screen`), never a relative file
path.

## Progressive disclosure

| In SKILL.md (always loaded) | In references/ or docs/ (on-demand) |
|---|---|
| Quick-start commands | Full framework detail |
| Routing table | Edge cases |
| One worked example | Historical content |
| Script locations | Implementation details |

## Signal density — kill no-ops

Signal density is the second economy test, beneath the length budget. Delete any
line that doesn't change behaviour: if a competent agent would act identically
without it, it was a no-op. Agent-authored skills accumulate these, and they make
a skill harder to evaluate and maintain while burning tokens.

Three classes to strike:

- **Truisms** — "be thorough", "write a clear commit message", "make it
  readable". The agent already does this; the line adds nothing.
- **Restatement** — re-asserting a rule the skill already gave. A single HARD
  GATE may earn one echo; nothing else does.
- **Duplication** — the same guidance spread across three sections, or inline
  content that a referenced file already owns.

No-ops are context-specific: a phrase that steers one skill is dead weight in
another. The test is always the same — remove it, and check whether the output
moves. Apply it at write-time, then again before shipping. The `signal_density`
dimension in `workflows/skill-audit.js` scores it across the tree.

## When to add scripts

Add a `scripts/` helper when the operation is deterministic, would be
regenerated on every invocation, or needs explicit error handling. Scripts save
tokens, reduce variance, and are testable outside agent sessions.
