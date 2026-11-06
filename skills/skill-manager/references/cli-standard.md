# Small CLI standard

Aim: an API that is easy to compose. A small surface in front of the behaviour.

This standard applies to small CLIs and to agent-facing Python entrypoints that a `SKILL.md`, a workflow, or a reference tells the agent to run. Repository maintenance scripts that no skill names stay outside it.

## Rules

1. Any command with potentially destructive side effects has `--dry-run`. Writing a file, mutating a vault, and applying a change are side effects.
2. Use subcommands to disclose functionality gradually, one job at a time.
3. Error messages are descriptive and tell the agent what to do next.
4. `--help` text is rich. It states what the command does, lists the subcommands, and names the flags that change behaviour.
5. Machine-readable output, such as `--json`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean. The command finished with nothing to report. |
| 1 | Findings. The command ran and reported a problem. |
| 2 | Bad invocation. Stderr says what to pass next. |

## Checklist for authors

`python3 scripts/cli_lint.py <skill-dir>` mirrors this list. Each hit is advisory. `scripts/validate.sh` prints the same hits as warnings and still exits 0 when the structural checks pass.

- `--help` is usable. Help is enabled, and the parser description is a sentence of at least 20 characters.
- A `--json` flag, or a `--format` flag whose choices include `json`, is present.
- A command that writes a file, mutates a vault, or applies a change has `--dry-run`.
- Errors are specific. A bare `error` is a finding. On exit 2, stderr carries a message. A message under 20 characters includes the word try, use, or pass.

Rule 2 (subcommands) stays with the author.
