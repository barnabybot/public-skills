---
name: delete-comment
description: >-
  Run a code-comment burn-down pass across public-skills or a named skill,
  categorising comments into Tautology, Excuse, Stale, and Decision Record,
  extracting ADRs, filing issues for excuses, and tightening the comment
  ratchet baseline.
---

# delete-comment

Run a repeatable code-comment burn-down pass in `barnabybot/public-skills`.
Substitute `<my codebase | this section of the code>` below with the requested
repository or skill scope before starting.

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

## Repository Guardrails

- **Directive and sentinel carve-out**: Leave shebangs (`#!`), licence or SPDX headers, machine sentinels (such as canon mirror markers `>>> BEGIN` / `<<< END`), and linter or type-checker directives (`# noqa`, `# type:`, `# shellcheck`, `# frozen_string_literal:`, `@ts-expect-error`, `eslint-disable`, `stylelint-disable`, `swiftlint:`) untouched.
- **ADR destination**: Write extracted Decision Records to `docs/adr/NNNN-<slug>.md` and update `docs/adr/README.md` before deleting inline comments.
- **Excuse issues**: File one GitHub issue per distinct hacky implementation in this repository's issue tracker (`gh issue create`), naming the file, symbol, and underlying defect, before deleting the inline comment.
- **Ratchet verification**: Tighten and verify the ratchet after every pass:

```bash
python3.12 scripts/check_code_comments.py --root . --write-baseline
python3.12 scripts/check_code_comments.py --root . --ratchet
python3.12 scripts/check_binary_ratchet.py --repo .
```
