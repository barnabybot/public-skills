---
name: skill-manager
version: 1.0.0
fallback: "If validate.sh cannot run, apply references/review-checklist.md by hand."
attribution: "Structure and progressive-disclosure patterns adapted from Artem Zhutov's skill-management skill"
description: >-
  Create and review agent skills. Use for /skill-manager, "new skill", "review this skill",
  "audit my skills", skill descriptions, validation, naming or symlink issues.
allowed-tools: [Read, Grep, Glob, Bash, Write, Edit, AskUserQuestion]
---

# skill-manager — authoring and quality guide

The router for skill authoring. Skills are self-contained folders: a SKILL.md
router under 100 lines, with detail pushed into `references/`, `workflows/`,
`scripts/`, `templates/`, and `docs/`. Read the reference for the task in hand.

## Intake

One panel, before any reference under `references/` or any skill folder is
read. Skip what the request settles; say what you read in the line above the
panel.

**Task** — What is the job?
- Create — scaffold a new skill: folder, frontmatter, description, the length budget (`references/authoring-spec.md`)
- Review — the pre-ship pass on a skill: `scripts/validate.sh`, then the checklist (`references/review-checklist.md`)
- Audit — every SKILL.md in the tree scored on seven dimensions, worst first (`workflows/skill-audit.js`)
- Plumbing — names, renames and symlinks (`references/naming-conventions.md`, `references/discovery-workflow.md`)
- settled by: "new skill" (Create); "review" or "before I ship" (Review); "audit" (Audit); "symlink" or "rename" (Plumbing)

**Target** — Which skills?
- Named — one skill, by name or path, given after the panel
- Branch diff — every skill the current branch touches against `origin/main`
- Whole tree — every skill under the skills root
- settled by: a skill name or path (Named); Audit (Whole tree); Create (the new skill)

**Standard** — Which bar?
- Automated — `scripts/validate.sh` alone: FAILs block, WARNs advise (the default)
- Full checklist — the automated bar plus the human-judgement items: voice, description quality, collision, worked example, `parent:`
- settled by: "full review" or "checklist" (Full checklist); Audit (the seven dimensions)

**Delivery** — What comes back?
- Report — findings and the fixes named; nothing edited (the default)
- Apply — the fixes made in the working tree, one edit per file, diffs shown
- settled by: "fix it" (Apply)

Text fields, one message after the panel: the skill name or path, and for
Create the purpose in one sentence and the trigger phrases.

## References

| Task | Read |
|---|---|
| Folder layout, frontmatter fields, the description spec, length budget, progressive disclosure, when to add scripts | `references/authoring-spec.md` |
| The full pre-ship review checklist + when-to-create-vs-extend | `references/review-checklist.md` |
| Folder/name rules, families, native vs adopted children, renaming | `references/naming-conventions.md` |
| Where the harness looks for skills, symlinking, validating, auditing the whole tree | `references/discovery-workflow.md` |
| The intake panel: one panel first, every option explained, host rendering | `references/intake-spec.md` |

## The two non-negotiables

- **Description quality.** The `description:` field is the only text the agent
  reads when deciding to load a skill. ≤1024 chars, third person, naming
  concrete trigger phrases and the slash command. See
  `references/authoring-spec.md`.
- **Length budget.** SKILL.md under 100 lines; 100-200 warns; over 200 splits
  into references. Parent routers may reach 200 but no further. Content used
  <20% of the time or over 50 lines moves to a sibling file.

## Validate before shipping

`scripts/validate.sh <skill-dir>` is the single automated bar — the
machine-checkable subset of the review checklist. Run it on any skill; FAILs
block, WARNs are advisory. Human-judgement items (voice, description quality,
collision, worked example, `parent:` field) stay manual.

```bash
scripts/validate.sh ~/.claude/skills/my-skill
```

## Audit the whole tree

`workflows/skill-audit.js` is a Claude Code dynamic workflow (run via the
`Workflow` tool, not Bash) that scores every SKILL.md on seven dimensions,
ranks worst-first, and names the single highest-value fix plus the top five:

```
Workflow({scriptPath: "<this skill>/workflows/skill-audit.js", args: {root: "~/my-skills"}})
```

It returns `{ count, ranked, synthesis, html }`. Write the `html` to a dated
report (e.g. `YYYY-MM-DD skill-audit.html`) and action the top five. Details in
`references/discovery-workflow.md`.
