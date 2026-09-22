# public-skills

Six agent skills and one `AGENTS.md`, taken from a working setup and rewritten
so they run on somebody else's machine.

They are for people who have started using a coding agent - Claude Code, Codex,
or another CLI harness - and want more from it than one conversation at a time.

| Skill | What it does |
|---|---|
| [`orchestrator`](skills/orchestrator/) | Run several agents at once. One coordinator spawns named workspaces, routes each job to a model and effort level, reads their screens, and relays your comments. Owns the routing table, the tiering rule and the resolver. |
| [`cmux`](skills/cmux/) | The mechanics underneath: spawn a workspace, write the session note, close it cleanly. Two scripts; it calls the orchestrator to route. |
| [`handoff`](skills/handoff/) | Move context from one session to the next before it runs out, as a new workspace, a clipboard brief, or a parked note. |
| [`recall`](skills/recall/) | Read your own history. What you did yesterday, or last week, or on a topic, from the transcripts your agent already writes. |
| [`vault-setup`](skills/vault-setup/) | Scaffold a Markdown knowledge vault with the folder tree, templates and instruction file for its type. |
| [`editorial-review`](skills/editorial-review/) | Review prose and argument across six lenses. Catches buried ledes, weak arguments and the specific tells that mark machine-written text. |

[`AGENTS.md`](AGENTS.md) is the instruction file that governs all of it: how an
agent should think before it codes, how small a change should be, when it must
stop and show you one example before doing something fifty times, and how to
write in a voice that does not read as generated.

## What this assumes

Be clear before you clone it.

- **Two skills need [cmux](https://www.cmux.dev).** `orchestrator` and `cmux`
  drive a terminal multiplexer built for running several agents side by side.
  Without it, read them for the patterns and use something else for the
  mechanics.
- **`recall` reads transcripts on disk.** `~/.claude/projects/` for Claude Code
  and `~/.codex/sessions/` for Codex, which is where those tools already write
  them. The graph mode additionally wants `networkx` and `pyvis`.
- **Three skills need nothing.** `handoff` (except for its auto-spawn mode),
  `vault-setup` and `editorial-review` run anywhere.
- **`orchestrator` needs the `cmux` skill, and `cmux` needs `orchestrator`.**
  The orchestrator owns the routing table and the resolver; the cmux helper
  calls it to route a spawn. Install the pair.
- **`orchestrator` needs PyYAML** (`pip install PyYAML`). It is the only
  non-stdlib dependency in the repository, and it fails with that install line
  rather than a traceback.
- **The routing table is a placeholder.** Every row in the orchestrator's
  `SKILL.md` is marked `basis: practice`, which means a shape rather than a
  finding about your stack. Its second provider resolves to deliberately invalid
  model IDs, so an unconfigured provider fails loudly instead of launching the
  wrong model. Edit both it and `references/routing-metadata.yaml` before you
  spawn anything you care about.

## Where things get written

Four of the skills write session notes and handoff briefs. They agree on one
root, set by one environment variable:

```bash
export AGENT_NOTES="$HOME/agent-notes"    # the default, if you set nothing
```

| Path | Holds |
|---|---|
| `$AGENT_NOTES/Sessions/` | One note per session, `YYYY-MM-DD <slug>.md`, with `agent:`, `model:`, `effort:` and `status:` in the frontmatter |
| `$AGENT_NOTES/Sessions/Handoffs/` | Handoff briefs, one per handoff |

The folder is created on first use, so nothing needs setting up. Point it at a
folder inside a notes vault if you keep one - Obsidian, or anything else that
reads Markdown - and the notes become browsable.

## Install

A skill is a folder with a `SKILL.md` in it. Put the folder where your harness
looks for skills, and the harness reads the `description:` line to decide when
it applies.

**Claude Code** reads `~/.claude/skills/`:

```bash
git clone https://github.com/barnabybot/public-skills.git ~/public-skills
mkdir -p ~/.claude/skills
ln -s ~/public-skills/skills/recall ~/.claude/skills/recall
```

Symlink each one you want. Restart Claude Code, then type `/recall` to check it
loaded. Project-scoped instead of global? Use `.claude/skills/` inside the
project.

**Codex CLI** reads `~/.codex/skills/`. Same shape:

```bash
mkdir -p ~/.codex/skills
ln -s ~/public-skills/skills/handoff ~/.codex/skills/handoff
```

**Another harness.** A `SKILL.md` is Markdown with YAML frontmatter, so most of
these read as plain instructions. Paste the file into your system prompt, or
point your tool at the folder. `orchestrator` and `cmux` are the two that need
real scripts on disk.

**The instruction file.** Copy `AGENTS.md` to the root of a project, and
symlink `CLAUDE.md` to it so both tools read one canon:

```bash
cp ~/public-skills/AGENTS.md ./AGENTS.md
ln -s AGENTS.md CLAUDE.md
```

Then edit it. The file paths in it are conventions, and the rules above them are
the part worth keeping.

## Check it works

```bash
# The routing table resolves, and no workspace is spawned
skills/cmux/scripts/spawn-workspace.sh test --tier E --dry-run

# The routing table and metadata are structurally valid
python3 skills/orchestrator/scripts/check.py --no-live --no-log

# The resolver's own suite, against invented capacity fixtures
python3 skills/orchestrator/scripts/test_resolve.py

# The helper's routing, end to end through the orchestrator
skills/cmux/scripts/test-spawn-workspace.sh

# The session-note guard on close
skills/cmux/scripts/test-close-workspace.sh

# Yesterday's sessions, read from your own transcripts
python3 skills/recall/scripts/recall-day.py list yesterday --all-projects
```

## What these came from

A working setup that runs several agents across a few Macs. That original is
private, and its skills reach into one person's folders, notes and
subscriptions. Everything here was rewritten to remove those assumptions: the
paths are configurable, the routing table is generic, and the worked examples
name no real file.

Some of what makes a rule worth following is the incident behind it. Those are
kept, with the names taken out - a worker that authorised a gate nobody meant to
authorise, a relay that named the wrong element, a handoff that asserted a
launcher that never ran. The rules read better with them in.

## Licence

Not yet set. Ask before reusing this in something you ship.
