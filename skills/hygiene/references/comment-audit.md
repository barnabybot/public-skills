# Code-Comment Burn-Down and Ratchet

Use this taxonomy during Pillar 2 of `/brun-hygiene` to shed comment noise
without losing real architectural context. Keep comments only for licences,
shebangs, lint or type directives, machine sentinels, and external constraints
that code cannot express.

## Four Comment Categories

| Category | Definition | Required Action |
| --- | --- | --- |
| **Tautology** | Restates what is already visible from reading the code | Delete the comment |
| **Stale** | References old behaviour, deleted symbols, or retired paths | Delete the comment |
| **Excuse** | Justifies a hack, workaround, or skipped invariant so it persists | Delete the comment and file a GitHub issue for the underlying defect |
| **Decision Record** | Captures a non-obvious architectural or contract constraint | Move it into `docs/adr/NNNN-<slug>.md`, then delete the inline comment |

## Ratchet Workflow

1. **Measure baseline**: run the repository's comment ratchet check (for example `check_code_comments.py --ratchet`) and count non-directive comment lines per directory.
2. **Estimate lines shed**: report total non-directive comment lines removable across the target scope before editing.
3. **Burn down in small PRs**: apply the four actions above file by file, extracting ADRs before deleting decision-record comments and filing issues for excuses.
4. **Tighten the ratchet**: update the committed baseline (`--write-baseline`) so new non-directive comments fail pre-commit and CI while existing debt only shrinks.
5. **Keep it repeatable**: ensure the pre-commit hook and CI enforce the ratchet on added lines, and keep `/brun-hygiene` (or a repo-local `/delete-comment` alias) available for future burn-down passes.
