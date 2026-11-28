# Home Repo instructions

This repository can serve as `<your-home-repo>`. Keep global steering in
[home/global.md](home/global.md). Keep the repository map and local policy here.
Read both files before cross-repo work.

## Instruction files and harness symlinks

Symlink the global file into every provider instruction location your harnesses
read:

```sh
ln -s <your-home-repo>/home/global.md ~/.claude/CLAUDE.md
ln -s <your-home-repo>/home/global.md ~/.codex/AGENTS.md
ln -s <your-home-repo>/home/global.md ~/.gemini/GEMINI.md
```

Use an absolute path for `<your-home-repo>`. Create parent directories first.
Review existing files and merge your rules before replacing them. Keep root
`AGENTS.md` as the Home Repo map. Link root `CLAUDE.md` and `GEMINI.md` to
`AGENTS.md` so harnesses that check only one filename never silently skip your
rules. (If you prefer a single unified file in your private Home Repo, fold
global steering into root `AGENTS.md` and point the three global symlinks there.)

Optional `home/harness/` files can hold declarative settings templates such as
`claude-settings.json` or `codex-config.toml`. Merge shared keys into live
config files rather than overwriting machine-local state. Keep credentials and
machine-specific paths outside tracked settings. This repository supplies no
personal settings.

## Customise the map

Complete this checklist before adopting the layout:

- Replace `<your-home-repo>` with your absolute checkout path (for example
  `~/Repos/home`).
- Set `$VAULTS_ROOT` to `<your-vaults-root>` (for example `~/Obsidian`) and map
  each project and vault below. Keep Git repositories under `~/Repos/` and never
  nest a Git repo inside a synced vault.
- Set `$AGENT_NOTES` to your agent-notes root (for example `$VAULTS_ROOT/Agents`).
  The skills default to `~/agent-notes`.
- Replace `<provider-a-model-id>` and `<provider-b-model-id>` in your routing
  configuration with supported IDs. Configure provider access and effort levels.
- Read each destination's own `AGENTS.md` before changing its files.

| Destination | Path | Instructions |
|---|---|---|
| Home Repo | `<your-home-repo>` | This file and `home/global.md` |
| Repositories | `~/Repos/<repo>` | Repository `AGENTS.md` |
| Vaults | `$VAULTS_ROOT` | Each vault's `AGENTS.md` |
| Session records | `$AGENT_NOTES` | Agent-notes `AGENTS.md` |
| Scratch renders | `~/Scratch/YYYY-MM-DD/` | Throwaway previews and exports |

## Personal and work boundary

Run a separate Home Repo on a work laptop. Use this repository (or a scrubbed
fork of portable skills) as the bridge for generic capabilities you want in both
environments. Enforce two rules across every vault and repo:

- **Boundary Rule.** Never move confidential project, client or employer
  material into personal vaults, global instructions or public repositories.
- **Leaving Test.** Every project or work vault must remain complete and
  intelligible if handed over without your personal Home Repo.

## Skill catalogue and locations

[README.md](README.md) lists the shared skills and their prerequisites.
Shared skills live in `skills/<name>/SKILL.md` (each kept at or under 100 lines,
with deeper guides in `references/` and `workflows/`). Mount them into every
global skills folder your harnesses read:

- `~/.agents/skills/` (T3 Code, Codex, Antigravity and Agent Skills hosts)
- `~/.claude/skills/` (Claude Code)
- `~/.codex/skills/` (Codex CLI)
- `~/.cursor/skills/` (Cursor)

Keep repo-local skills at `.agents/skills/<name>/SKILL.md`. Link each tool's
local skill folder to the same source with relative symlinks:

```sh
mkdir -p .claude/skills .cursor/skills
ln -s ../../.agents/skills/<name> .claude/skills/<name>
ln -s ../../.agents/skills/<name> .cursor/skills/<name>
```

Use `model-routing` (`skills/model-routing/scripts/preflight.py`) for
deterministic model preflight across hosts (`--host t3 | cmux | cli`), the
provider health circuit breaker and automated 2-hop takeovers. Use
`orchestrator` explicitly for multi-item queues, multi-repo coordination,
parallel fan-outs and session handoffs, reading its `references/hosts.md`
before choosing a transport. Install `cmux` only for cmux workspace control.

## Personal CLI front-door (optional)

Keep deterministic routing, sync, vault search and operational commands in
scripts rather than long prompt rules. Out of the box, agents call
`python3 skills/model-routing/scripts/preflight.py` directly.

In your private Home Repo, you can front those scripts behind one thin wrapper
executable on `PATH` (for example `b <domain> <verb>`, such as `b route
preflight --json`, `b sync --check --json`, `b qmd query`, `b sessions`) so
every runtime invokes the same short command without hardcoding repo paths.
Keep personal credentials, calendar, mail and machine-specific domains inside
your private Home Repo wrapper rather than in portable skills.

## Verification gates

State the goal and a short plan with a check for each step. Read current source
before editing. Keep changes within the request.

Run the skill validator after skill edits. Run the affected self-tests after
script changes. For this repository, start with these checks:

```sh
./.agents/skills/verify-public-skills/scripts/validate-all
python3 skills/model-routing/scripts/check.py --no-live --no-log
python3 -m unittest discover -s skills/model-routing/scripts -p 'test_*.py'
python3 -m unittest discover -s skills/skill-manager/scripts/tests -p 'test_*.py'
python3 -m unittest discover -s skills/session-intelligence/scripts/tests -p 'test_*.py'
python3 skills/graph/scripts/selftest.py
python3 scripts/check_binary_ratchet.py --repo .
python3 scripts/check_code_comments.py --root . --ratchet
```

Enable the local pre-commit hooks with `git config core.hooksPath .githooks`.
Record non-obvious tooling decisions in `docs/adr/` rather than inline code
comments.

Inspect rendered HTML, CSS, SVG, PDF and slides visually before declaring them
complete. Source checks, rendered review and publication approval are separate
gates. Report what passed with evidence. For each unverified check, state its
cause and the next check. Record repeated failures and add a regression check.

The cmux and editorial checks also run directly. Hyphenated test filenames need
explicit invocations because unittest discovery skips them.

```sh
bash skills/cmux/scripts/test-spawn-workspace.sh
bash skills/cmux/scripts/test-close-workspace.sh
python3 -m unittest discover -s skills/cmux/scripts -p 'test*.py'
python3 skills/cmux/scripts/test-group-header.py
python3 skills/cmux/scripts/test-close-idle-codex.py
python3 -m unittest discover -s skills/editorial-review/scripts/tests
python3 -m unittest discover -s skills/hygiene/scripts -p 'test_*.py'
```

## Branch hygiene

Work in an isolated branch or worktree. Treat the default branch as protected.
Apply the Thin-Slice Gate in `home/global.md` before public pushes. A website
push may publish the live site. Stage named files and keep commit hooks.

Remote workers clean up their own branches after merge or closure. Preserve the
default branch, open PR heads and uncertain ownership. Read the expected tip,
verify the branch is eligible, then use an expected-tip lease for deletion:

```sh
git push origin --force-with-lease=refs/heads/<branch>:<expected-sha> --delete <branch>
```

A changed tip must stop deletion. Recheck ownership and PR state before retrying.

## Child project or vault starter

Copy this template into each destination and replace its placeholders:

```markdown
# Project instructions

## Purpose

<What this project or vault holds.>

## Paths and boundaries

- Deliverables go to <destination>.
- Working evidence goes to <scratch-or-operations-folder>.
- <Protected paths> require separate approval.

## Skills

Read <relevant-skill-path>/SKILL.md for <task>.

## Verify

Run <validator-or-self-test>. Inspect <rendered-output> visually.
Record evidence and any unresolved checks before declaring completion.
```
