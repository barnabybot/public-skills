# Hygiene workflows

Hygiene offers focused `comments`, `ci`, `architecture` and `safety` routes.
The current entrypoint links three workflow documents. Safety adds eleven
checks with an audit-first approval boundary.

## Sub-features

- `hygiene-workflow-links`. Open all three linked workflow documents.
- `hygiene-safety-handoff`. Read all eleven checks and record the audit limits.
- `hygiene-ci-plan`. Preview the audit's GitHub endpoints with `--dry-run`.
- `hygiene-architecture-handoff`. Read the conditional web-scan route.

## How to get to it (user POV)

Use `/hygiene`, select the current repository, a focused pillar and Audit only.
Comments leads to the four-category review and ADR workflow. CI leads to the
150-run audit and timing budgets. Safety leads to the eleven-check prompt.
Architecture includes a conditional web scan when frontend code is present.

Source: [Hygiene](../../../../skills/hygiene/SKILL.md), lines 20-59,
[Safety](../../../../skills/hygiene/workflows/safety-audit.md), and
[CI CLI](../../../../skills/hygiene/scripts/ci_audit.py), lines 233-275.

## Live recipe

Use [Launch and Doctor](../SKILL.md) in a fresh CLI session, then run:

```bash
python3 - <<'PY'
import re
from pathlib import Path

entry = Path("skills/hygiene/SKILL.md")
links = re.findall(r"\]\((workflows/[^)]+)\)", entry.read_text())
assert len(links) == len(set(links)) == 3, links
for link in links:
    target = entry.parent / link
    assert target.is_file() and target.stat().st_size > 0, target
    print(f"ok workflow {target}")
safety = (entry.parent / "workflows/safety-audit.md").read_text()
checks = [int(n) for n in re.findall(r"^(\d+)\. Check:", safety, re.M)]
assert checks == list(range(1, 12)), checks
print(f"ok safety checks={len(checks)}")
PY
python3 skills/hygiene/scripts/ci_audit.py --repo barnabybot/public-skills --dry-run --json
nl -ba skills/hygiene/SKILL.md | sed -n '20,59p'
nl -ba skills/hygiene/workflows/safety-audit.md
```

Keep exit 0, the three resolved paths, eleven numbered checks and JSON with
`dry_run: true`, `repo: barnabybot/public-skills` and `limit: 150`. Read the
printed routes and safety prompt. Confirm audit first, secret values kept out
of output, in-repo fixes separated from manual steps, and approval before edits.
Record one repository-scoped safety walkthrough under all eleven headings.
Mark unavailable host or account evidence as unknown and rank concrete findings.

## Gotchas

- Markdown handoffs and the local CI plan are the verification surface here.
  Structural catalogue validation alone supplies no workflow evidence.
- Live CI timings, branch protection, token scopes and host settings require
  separate evidence. The dry-run returns before making GitHub API calls.
- The published `python3 scripts/ci_audit.py` examples need a working-directory
  clarification. From the repository root they fail because the script lives
  under `skills/hygiene/scripts/`. Record this product documentation gap.
- The conditional web scan uses `npx` and network access. Reading its route
  leaves scanner execution and browser compatibility findings unverified.
- Keep the audit read-only. Product changes and external writes need their
  own approval.
