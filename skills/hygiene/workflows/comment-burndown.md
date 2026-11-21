# Code-Comment Burn-Down Workflow

Follow the prompt below verbatim during Pillar 2 of `/hygiene` (or when running
a focused `comments` pass). Substitute `<my codebase | this section of the
code>` with the approved repository or module scope before starting.

## Prompt (Verbatim)

Take a look at every code comment in `<my codebase | this section of the code>`.

Categorise each comment as:

- Tautology: simply repeats what is already visible from the code
- Excuse: many comments allow the agent to get away with a hacky implementation, which then gets propagated through the code
- Stale: references code or implementation information that is no longer relevant
- Decision Record: documents an important, non-obvious decision about the code

For each comment, take this action:

- Tautology/Stale: delete the comment
- Excuse: delete the comment and file an issue to fix the hacky implementation
- Decision Record: move it into an ADR

Once this is done:

- Create a lint rule banning comments for `<my codebase | this section of the code>`
- Take a ratchet approach, assuming not all comments will be deleted this PR
- Create a `/delete-comment` skill in this repository so we can repeat this process later
- Estimate for me how many lines of code we'll shed by deleting all comments

## Repository Plumbing

Apply these operational guardrails alongside the prompt above:

- **Audit-only gate**: When `/hygiene` runs in `Audit only` mode, inspect every comment in scope, classify it into the four categories, estimate total lines shed, and list proposed deletions, issues to file, and ADRs to extract without modifying files. Execute edits only in an isolated branch or worktree after approval.
- **Syntax and directive carve-out**: Leave shebangs (`#!`), licence or SPDX headers, machine sentinels (such as canon mirror markers), and linter or type-checker directives (`# noqa`, `# type:`, `@ts-expect-error`, `eslint-disable`) untouched. Every other comment falls into the four categories above. Move Decision Records into ADRs rather than keeping them inline.
- **ADR destination**: Write each Decision Record to `docs/adr/NNNN-<slug>.md` (incrementing the existing sequence) before deleting the inline comment.
- **Lint rule and ratchet**: If the repository already enforces a comment ratchet (such as `check_code_comments.py --ratchet` in `.githooks/pre-commit` and CI), run it and tighten the baseline (`--write-baseline`) after deletions. Otherwise add a lint rule or pre-commit and CI ratchet that rejects newly added non-directive comments while letting existing counts only fall.
- **Repeatable skill**: If the repository does not already have a repo-local `/delete-comment` skill (or explicit project alias to this workflow), create `.agents/skills/delete-comment/SKILL.md` (with harness symlinks where the repo uses them) containing this workflow so future burn-down passes stay one command away.
- **Excuse issues**: File one issue per distinct hacky implementation in the repository's issue tracker before closing the PR, citing the file, symbol, and underlying defect.
