# Review checklist

Before shipping any skill:

- [ ] Description: ≤1024 chars, third person, concrete triggers
- [ ] SKILL.md: under 100 content lines (or justified parent router)
- [ ] Signal density: no no-ops — every line changes behaviour (cut truisms, restatement, duplication)
- [ ] No time-sensitive content (move dated claims to a changelog or notes file)
- [ ] Consistent terminology (one name per concept across all files)
- [ ] At least one fully-worked example for the primary invocation
- [ ] References one level deep (SKILL.md → references/foo.md, never two hops)
- [ ] Voice rules clear (whatever your instruction file sets for prose)
- [ ] No collision with existing skill descriptions (grep every `description:` in the tree)
- [ ] `parent:` field set for all family children
- [ ] `fallback:` set for any skill whose scripts can fail to run

## The automated bar

`scripts/validate.sh <skill-dir>` is the single automated quality bar — the
machine-checkable subset of this checklist (structure, fields, ≤1024-char
description, scripts/references placement, line budget). Run it on any skill;
FAILs block, WARNs are advisory. The human-judgement items (voice, description
quality, collision, worked example, `parent:` field) stay manual.

## When to create vs extend

| Need | Solution |
|---|---|
| Always-needed context | CLAUDE.md or AGENTS.md |
| User triggers specific prompt | Skill |
| Repeated workflow with scripts | Skill |
| Existing skill covers 80% | Extend with a workflow/ file |

Before creating: check for collisions, check if it belongs in an existing skill,
check for an existing template to reference.
