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

`scripts/skill_audit.py` and `workflows/skill-audit.workflow` discover every
`SKILL.md` under a flat (`<root>/<skill>/SKILL.md`) or family-grouped
(`<root>/<family>/<skill>/SKILL.md`) skills root (`$SKILLS_ROOT` or
`~/my-skills`), score each on seven dimensions (description, line budget,
progressive disclosure, self-containment, naming, freshness, and signal density;
total /35), rank worst-first, and synthesise the single highest-value fix plus
the top five to action.

- Via portable CLI (`agy`, `claude`, `codex`, `grok`, or `muse`):

```bash
python3 scripts/skill_audit.py discover --root ~/my-skills --json
python3 scripts/skill_audit.py run --root ~/my-skills --harness auto \
  --out-html "$AGENT_NOTES/Audits/YYYY-MM-DD skill-audit.html" --json
```

- In hosts exposing `run_workflow`:

```text
run_workflow(
  ScriptPath="<this skill>/workflows/skill-audit.workflow",
  Args={"root": "~/my-skills", "outHtml": "$AGENT_NOTES/Audits/YYYY-MM-DD skill-audit.html"}
)
```

It returns `{ count, ranked, synthesis, html }`. Save the returned `html` to a
dated report and action the top five.
