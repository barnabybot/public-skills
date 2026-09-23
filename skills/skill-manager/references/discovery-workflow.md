# Discovery, validating, and auditing

## Where the harness looks

Claude Code discovers skills at `~/.claude/skills/*/SKILL.md`, one level deep
only. Codex reads `~/.codex/skills/`. A skills tree organised by family is two
levels deep (`<family>/<skill>/SKILL.md`), so one symlink to a family folder
makes the family router visible and hides all its children.

The fix is one symlink per skill:

```bash
SKILLS_ROOT=~/my-skills          # where the canonical tree lives
for d in "$SKILLS_ROOT"/*/ "$SKILLS_ROOT"/*/*/; do
  [ -f "$d/SKILL.md" ] || continue
  ln -sfn "${d%/}" ~/.claude/skills/"$(basename "$d")"
done
```

Run it after creating a new skill or when a skill does not surface. The family
router keeps its own symlink; the per-child links sit alongside it.

Codex follows directory symlinks recursively, so it can expose `SKILL.md` files
nested inside a skill's own folders. If that happens, give Codex a shallow copy
per skill that holds only the frontmatter and one line pointing at the full
source.

## Validating

`scripts/validate.sh <skill-dir>` is the single automated quality bar — the
machine-checkable subset of the review checklist (structure, fields,
≤1024-char description, scripts/references placement, line budget). Run it on
any skill; FAILs block, WARNs are advisory. The human-judgement items (voice,
description quality, collision, worked example, `parent:` field) stay manual.
It is Bash by deliberate exception to the Python default, so it runs on minimal
hosts where only coreutils are guaranteed.

## Auditing the whole tree

`workflows/skill-audit.js` is a Claude Code dynamic workflow (run via the
`Workflow` tool, not Bash) that scores every `SKILL.md` under a root against the
rubric. A Haiku sub-agent grades each skill on seven dimensions (description,
line budget, progressive disclosure, self-containment, naming, freshness,
signal density), the script ranks worst-first, and one Opus agent names the
single highest-value fix plus the top five to action. It finds the skills
itself; pass `args.root` or set `SKILLS_ROOT`, or it reads `~/.claude/skills`:

```
Workflow({scriptPath: "<this skill>/workflows/skill-audit.js", args: {root: "~/my-skills"}})
```

It returns `{ count, ranked, synthesis, html }`. Write the returned `html` to a
dated report (e.g. `YYYY-MM-DD skill-audit.html`) and action the top five.
