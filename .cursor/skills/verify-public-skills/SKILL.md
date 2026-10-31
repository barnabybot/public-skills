---
name: verify-public-skills
description: >
  Check barnabybot/public-skills (published agent skills for knowledge workers)
  by running skill-manager validate.sh across every skills/*/ folder. Use after
  editing a public skill, before a release ZIP, or when AGENTS.md / skill
  frontmatter may have drifted. CLI surface — no server.
---

# verify-public-skills

Proof under `scratchpad/verify-public-skills/`.

## Launch

```bash
test -f AGENTS.md
test -x skills/skill-manager/scripts/validate.sh
```

Ready when validate.sh is executable.

## Doctor

```bash
test -f skills/skill-manager/scripts/validate.sh
bash skills/skill-manager/scripts/validate.sh skills/recall | tail -5
echo 'ok: ready'
```

## Drive

```bash
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
.cursor/skills/verify-public-skills/scripts/validate-all
```

Expect summary lines `ok <name>` for each skill and `exit.txt` of `0`.

Single skill: `bash skills/skill-manager/scripts/validate.sh skills/<name>`.

Recipes: [Catalogue](features/catalogue.md), [Validate one](features/validate-one.md), [AGENTS.md](features/agents-md.md).

## Evidence

Per-skill `.txt` / `.exit` plus `summary.txt` under the run dir. Cleanup leaves them.

## Cleanup

No server. Leave evidence.

## Helpers

`.cursor/skills/verify-public-skills/scripts/validate-all`
