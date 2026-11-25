---
name: verify-public-skills
description: >
  Check barnabybot/public-skills through catalogue validation, one-skill checks,
  root instructions and hygiene workflow handoffs. Use after editing a public
  skill, before a release ZIP, or when instructions or frontmatter may have
  drifted. Runs local CLI commands without a server.
---

# verify-public-skills

Default proof goes under `scratchpad/verify-public-skills/<RUN_ID>/`.
Set `SHOT_OUT` to an absolute directory to retain proof elsewhere.

## Launch

Use a fresh isolated CLI session for each drive at the repository root. Run
`bash --noprofile --norc -euo pipefail -c '<launch checks; feature recipe>'`.
Prepend these checks to each recipe inside that shell:

```bash
test -s AGENTS.md
test -x skills/skill-manager/scripts/validate.sh
test -x .cursor/skills/verify-public-skills/scripts/validate-all
```

Ready when instructions are non-empty and both scripts are executable.
No agent login is required.

## Doctor

```bash
set -euo pipefail
test -s AGENTS.md
test -x skills/skill-manager/scripts/validate.sh
test -x .cursor/skills/verify-public-skills/scripts/validate-all
bash skills/skill-manager/scripts/validate.sh skills/recall | tail -5
echo 'ok: ready'
```

Run Doctor before the first drive and after any failed drive. Keep the shell's
pipeline failure handling enabled so a failed validator fails Doctor.

## Drive

```bash
export RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
export SHOT_OUT="${SHOT_OUT:-$PWD/scratchpad/verify-public-skills/$RUN_ID}"
.cursor/skills/verify-public-skills/scripts/validate-all
```

Require process exit 0, one `ok <name>` for every `skills/*/SKILL.md` entry,
all per-skill `.exit` files of `0`, and `exit.txt` of `0`. Warnings advise;
structural validation does not replace each skill's human review.

Single skill: `bash skills/skill-manager/scripts/validate.sh skills/<name>`.

Recipes: [Catalogue](features/catalogue.md), [Validate one](features/validate-one.md),
[AGENTS.md](features/agents-md.md), [Hygiene workflows](features/hygiene-workflows.md).

## Evidence

Keep the command, process exit, stdout and stderr for each drive. Catalogue
also writes per-skill `.txt` / `.exit`, `summary.txt` and `exit.txt`. Use a
different output directory for each drive because the helper replaces files.

## Cleanup

Each CLI process exits after its command. Leave evidence uncommitted. If a
drive needs stopping, target only the PID or isolated process group it started.

## Helpers

`.cursor/skills/verify-public-skills/scripts/validate-all`
