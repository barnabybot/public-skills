# Home Repo instructions

This repository can serve as `<your-home-repo>`. Keep global steering in
[home/global.md](home/global.md). Keep the repository map and local policy here.
Read both files before cross-repo work.

## Two instruction files

Symlink the global file into the instruction locations used by your tools:

```sh
ln -s <your-home-repo>/home/global.md ~/.claude/CLAUDE.md
ln -s <your-home-repo>/home/global.md ~/.codex/AGENTS.md
ln -s <your-home-repo>/home/global.md ~/.gemini/GEMINI.md
```

Use an absolute path for `<your-home-repo>`. Create parent directories first.
Review existing files and merge your rules before replacing them. Keep root
`AGENTS.md` as the Home Repo map. Link root `CLAUDE.md` to `AGENTS.md` for tools
that use that name.

Optional `home/harness/` files can hold version-controlled tool settings such as
`claude-settings.json` or `codex-config.toml`. Keep credentials and machine-specific
paths outside tracked settings. This repository supplies no personal settings.

## Customise the map

Complete this checklist before adopting the layout:

- Replace `<your-home-repo>` with your absolute checkout path.
- Set `$VAULTS_ROOT` to `<your-vaults-root>` and map each project and vault below.
- Set `$AGENT_NOTES` to your agent-notes root. The skills default to `~/agent-notes`.
- Replace `<provider-a-model-id>` and `<provider-b-model-id>` in your routing
  configuration with supported IDs. Configure provider access and effort levels.
- Read each destination's own `AGENTS.md` before changing its files.

| Destination | Path | Instructions |
|---|---|---|
| Home Repo | `<your-home-repo>` | This file and `home/global.md` |
| Project | `<your-project-root>` | Project `AGENTS.md` |
| Vaults | `$VAULTS_ROOT` | Each vault's `AGENTS.md` |
| Session records | `$AGENT_NOTES` | Agent-notes `AGENTS.md` |

## Skill catalogue and locations

[README.md](README.md) lists the shared skills and their prerequisites.
Shared skills live in `skills/<name>/SKILL.md`. Mount them into
`~/.claude/skills/` and `~/.codex/skills/` for use across repositories.

Keep repo-local skills at `.agents/skills/<name>/SKILL.md`. Link each tool's
local skill folder to the same source with relative symlinks:

```sh
mkdir -p .claude/skills .cursor/skills
ln -s ../../.agents/skills/<name> .claude/skills/<name>
ln -s ../../.agents/skills/<name> .cursor/skills/<name>
```

Use `orchestrator` for coordination, model and effort routing, and handoffs
across T3 Code, cmux and CLI subagents. Read its `references/hosts.md` before
choosing a transport. Install `cmux` only for cmux workspace control.

## Verification gates

State the goal and a short plan with a check for each step. Read current source
before editing. Keep changes within the request.

Run the skill validator after skill edits. Run the affected self-tests after
script changes. For this repository, start with these checks:

```sh
./.agents/skills/verify-public-skills/scripts/validate-all
python3 skills/orchestrator/scripts/check.py --no-live --no-log
python3 -m unittest discover -s skills/orchestrator/scripts -p 'test_*.py'
```

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
