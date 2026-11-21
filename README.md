# public-skills

**Agentic engineering for knowledge workers on the command line.**

These skills are for people whose output is analysis, research, writing and
presentations, and who run AI agents in a terminal to produce it. You use
Claude Code or Codex already, or you are about to. You want several agents
working on one goal, each starting from the right context.

The repository holds nine skills, a [global contract](home/global.md) and a [Home Repo map](AGENTS.md), taken from a
working setup and rewritten so they run on somebody else's machine.

Download individual skills or the complete collection as ZIP files at
[barnabyrobson.org/downloads](https://barnabyrobson.org/downloads/). The page
includes installation guidance. This repository holds the source; each download
links to the source commit used to build it.

## Context engineering

An agent's output is only as good as the context it starts with. These skills
give every kind of context one home, and they decide which agent reads it.

| Layer | Where it lives | What it holds |
|---|---|---|
| Instructions | `AGENTS.md` at a project root and at each vault root | How an agent works in that place: where files go, what it must not touch, how it writes |
| Personal knowledge | A personal vault | Clippings, references, daily notes |
| Project work | One projects vault per project | Delivery material, meetings, stakeholders. Confidential content stays inside, and the vault closes when the project ends |
| Team method | An operations vault | Methods, proposals and meeting records that continue between projects |
| Compiled knowledge | A wiki vault, often beside the skill that reads it | Pages that an LLM compiles from raw sources. Knowledge grows with each new source and is not re-derived on every query |
| Runtime memory | An agents vault | Session notes, handoff briefs, audits, and evidence each skill keeps about its own work |

Each vault is a folder of Markdown with its own instruction file and its own
search collection. A search stays inside the boundary you give it, so client
material does not appear in a personal query. A handoff brief marks each claim
as VERIFIED (with the command that proved it) or ASSUMED, and the next agent
checks the claims its work depends on before it builds on them. `recall` reads
past sessions from the transcripts your tools already write.

## Multi-agent work

One coordinator divides a goal into jobs and selects each worker's model and
effort. `orchestrator` supports T3 Code, cmux and CLI subagents. Its
[host guide](skills/orchestrator/references/hosts.md) maps native tools, worktree
isolation and handoff. The optional `cmux` skill controls cmux workspaces.

Here a Claude orchestrator coordinates Codex and Grok workers on a demo
project, each in its own pane, and reports a gap one worker left:

![cmux workspace with a Claude orchestrator and Codex and Grok workers](skills/orchestrator/assets/preview.png)

| Skill | Its part |
|---|---|
| [`vault-setup`](skills/vault-setup/) | Creates each vault type with its folder tree, templates and instruction file |
| [`recall`](skills/recall/) | Finds past work in session notes where available, with native transcripts for missing detail or a setup without notes |
| [`retrospective`](skills/retrospective/) | Reviews a session or a bounded recent sample, verifies repeated problems and proposes small fixes. Uses recall for historical evidence |
| [`orchestrator`](skills/orchestrator/) | Coordinates T3 Code, cmux and CLI workers, resolves model and effort routing, and manages session handoffs. Requires PyYAML and a configured routing table. The cmux companion is optional |
| [`cmux`](skills/cmux/) | Controls workspaces and browser panes in the optional cmux terminal application. Calls orchestrator for routing policy |
| [`graph`](skills/graph/) | Renders a programme of work as an interactive dependency graph with dependency tracing, foldable branches and node inspection. Marks a node stale when its inputs change after its output was built |
| [`editorial-review`](skills/editorial-review/) | Checks prose and argument before it goes to a reader, including the tells that mark machine-written text |
| [`skill-manager`](skills/skill-manager/) | Writes and reviews new skills: description rules, a pre-ship checklist, a validator and a whole-tree audit |
| [`hygiene`](skills/hygiene/) | Runs post-event and weekly repository hygiene sweeps across Git hooks, binary ratchets, code-comment burn-downs and ADRs, 150-run CI audits and architecture debt triage |

`graph` turns one YAML state file into a page like this. Inspect nodes, filter the
DAG and expand the folded content-audit branch. The design-brief node reads stale
because its input changed after it was built
([source](skills/graph/assets/demo.state.yaml)):

![graph render of a sample website relaunch](skills/graph/assets/preview.png)

[home/global.md](home/global.md) supplies global steering.
[AGENTS.md](AGENTS.md) maps the Home Repo, shared skills and destinations.
Each project or vault has its own `AGENTS.md` for local instructions.

## Where these run

An agent is a model plus an agent runtime. These skills are written for the runtime:
an agent CLI such as Claude Code or Codex reads a `SKILL.md` and follows it. The runtime can run in
several places, and the skills load the same way in each.

| Where | Examples | Notes |
|---|---|---|
| A terminal | macOS Terminal, Windows Terminal | Shared skills and supported CLI subagents; cmux control requires cmux |
| A terminal workspace | cmux | Every skill. CLIs from several providers run side by side, and one agent can start, read and close the others |
| An editor | T3 Code, VS Code, Cursor | Run Claude Code or Codex in the editor's terminal or extension, on your own subscription. The editor's built-in agent bills through the editor's plan and chooses from its model list |
| A provider app | Claude desktop, Codex app | The same runtime in its own window, reading skills from the same folder |

Choose a host that exposes the tools your work needs. T3 Code uses native
orchestration tools. cmux uses terminal helpers. CLI subagents use the current
runtime's supported tools. Install the cmux companion only for cmux dispatch.

## Getting started

Install an agent runtime and choose an editor for its Markdown output.

1. **Choose how you pay for the model.** A subscription is the simplest start:
   Claude, ChatGPT, Gemini and Grok each come with their own agent CLI. You can
   also pay per token with an API key or through OpenRouter, or run a local
   model through Ollama, which costs nothing and is less capable. This choice
   decides which models you can use and how much work you get each week.
2. **Install the applications.**
   - A terminal or T3 Code. [cmux](https://cmux.com) is optional for users who
     want terminal workspaces controlled through the cmux companion skill.
   - The agent CLI for your provider, such as
     [Claude Code](https://claude.com/claude-code),
     [Codex](https://github.com/openai/codex), Gemini CLI or Grok CLI. The
     install steps below cover Claude Code and Codex; another CLI reads a
     `SKILL.md` as plain instructions. The cmux helper launches Claude Code,
     Codex and Grok.
   - [Obsidian](https://obsidian.md), where you read what your agents write.
     Any Markdown editor works.
3. **Open your chosen host, start the agent and sign in.**
4. **Paste this prompt:**

   ```
   Read README.md, AGENTS.md and home/global.md in public-skills.
   Tell me what each skill does and what you would install, then wait for my go.
   After I say go:
   1. Clone the repo to ~/public-skills and link every skill into your skills
      folder.
   2. Install PyYAML.
   3. Use vault-setup to create my agents vault, then set AGENT_NOTES to that
      vault's root in ~/.zshenv.
   4. Show me how home/global.md would merge with my global instructions.
      Keep AGENTS.md as the Home Repo map. My existing rules win where they
      conflict. Change no instruction links until I approve.
   ```

5. **Build your vaults with the agent.** The agents vault holds session notes
   and handoffs, so it comes first. Add a personal vault next, then one projects
   vault for each project. Open each one in Obsidian.
6. **Work with one agent for a few weeks.** Use `recall` to read back what you
   did. When running one agent at a time is what slows you down, ask it to start
   a second through `orchestrator`.

The sections below are the reference the agent reads in step 4. Read them
yourself before you say go.

## What this assumes

- **`recall` uses session notes when available.** It discovers the configured
  search collection or searches files under `$AGENT_NOTES/Sessions/`. Without
  notes, it reads native Claude Code and Codex transcripts. Graph mode also
  needs `networkx` and `pyvis`.
- **`retrospective` uses `recall` for earlier sessions.** Install both for the
  recent-sessions mode. A review of the visible conversation can run alone.
  `/retrospective recent sessions <project-path>` reviews up to ten eligible
  sessions and proposes zero to three fixes. It runs when invoked.
- **Two skills need nothing.** `vault-setup` and `editorial-review` run
  anywhere.
- **`orchestrator` needs PyYAML and a configured routing table.**
  It coordinates T3 Code, cmux and CLI agents. The optional `cmux` companion
  is needed only for cmux workspace dispatch. The standalone cmux host driver
  calls orchestrator for routing policy, so cmux users install both.
- **`orchestrator` and `graph` need PyYAML**
  (`python3 -m pip install --user PyYAML`). The orchestrator scripts and the
  graph renderer stop with that install line when it is missing. Apart from
  recall's graph mode, it is the only non-stdlib dependency in the repository.
- **`skill-manager` runs anywhere, except its audit.** `validate.sh` needs only
  Bash. The whole-tree audit is a Claude Code dynamic workflow, so it needs the
  `Workflow` tool.
- **The routing table is a placeholder.** Every category in the orchestrator's
  `references/routing-metadata.yaml` is marked `basis: practice`, which means a
  shape rather than a finding about your stack. Its second provider resolves to
  deliberately invalid model IDs, so an unconfigured provider fails loudly
  instead of launching the wrong model. Edit the table in `SKILL.md` and the
  metadata before you spawn anything you care about.

## Where things get written

Three of the skills write session notes and handoff briefs. They agree on one
root, set by one environment variable. Point it at the root of your agents vault,
in `~/.zshenv` so that every shell your agents start can read it:

```bash
export AGENT_NOTES="$HOME/vaults/agents"  # unset, it falls back to ~/agent-notes
```

| Path | Holds |
|---|---|
| `$AGENT_NOTES/Sessions/` | One note per session, `YYYY-MM-DD <slug>.md`, with `agent:`, `host:`, `model:`, `effort:` and `status:` in the frontmatter |
| `$AGENT_NOTES/Sessions/Handoffs/` | Handoff briefs, one per handoff |

The folders are created on first use. An agents vault made by `vault-setup`
already has `Sessions/`, `Sessions/Handoffs/` and `Ops/` at its root, so its
root is the right value.

## Install

A skill is a folder with a `SKILL.md` in it. Put the folder where your runtime
looks for skills, and the runtime reads the `description:` line to decide when
it applies.

**Claude Code** reads `~/.claude/skills/`:

```bash
git clone https://github.com/barnabybot/public-skills.git ~/public-skills
mkdir -p ~/.claude/skills
for d in ~/public-skills/skills/*/; do
  n=$(basename "$d")
  [ -e ~/.claude/skills/"$n" ] && echo "skip $n: already installed" || ln -s "$d" ~/.claude/skills/"$n"
done
```

This links all nine and leaves any skill you already have under the same name
alone. Restart Claude Code, then type `/recall` to check it loaded.
Project-scoped instead of global? Use `.claude/skills/` inside the project.

**Codex CLI** reads `~/.codex/skills/`. Clone as above, then:

```bash
mkdir -p ~/.codex/skills
for d in ~/public-skills/skills/*/; do
  n=$(basename "$d")
  [ -e ~/.codex/skills/"$n" ] && echo "skip $n: already installed" || ln -s "$d" ~/.codex/skills/"$n"
done
```

The skills ask their intake questions through Codex's `request_user_input`,
which needs `default_mode_request_user_input = true` under `[features]` in
`~/.codex/config.toml`.

**Another runtime.** A `SKILL.md` is Markdown with YAML frontmatter, so most of
these read as plain instructions. Paste the file into your system prompt, or
point your tool at the folder. `orchestrator` and `cmux` are the two that need
real scripts on disk.

## Adopt the Home Repo split

Keep global rules in [home/global.md](home/global.md). Keep your repository,
project and vault map in root [AGENTS.md](AGENTS.md). Review existing global
instructions and merge your rules before replacing a link. Create the tool
folders first, then use absolute paths for these links:

```sh
ln -s <your-home-repo>/home/global.md ~/.claude/CLAUDE.md
ln -s <your-home-repo>/home/global.md ~/.codex/AGENTS.md
ln -s <your-home-repo>/home/global.md ~/.gemini/GEMINI.md
```

Optional version-controlled `home/harness/` files may sit beside `home/global.md`.
Examples include `claude-settings.json` and `codex-config.toml`. Keep secrets
and private machine settings outside the repository.

Shared skills stay in `skills/<name>/`, linked into the global tool folders
shown above. Repo-local skills have one canonical source at
`.agents/skills/<name>/SKILL.md`. Use relative links for Claude and Cursor:

```sh
mkdir -p .claude/skills .cursor/skills
ln -s ../../.agents/skills/<name> .claude/skills/<name>
ln -s ../../.agents/skills/<name> .cursor/skills/<name>
```

Use the child instruction template in root `AGENTS.md` for projects and vaults.

## Check it works

```bash
# The routing table resolves, and no workspace is spawned
skills/cmux/scripts/spawn-workspace.sh test --tier systems --dry-run

# The routing table and metadata are structurally valid
python3 skills/orchestrator/scripts/check.py --no-live --no-log

# The resolver's own suite, against invented capacity fixtures
python3 skills/orchestrator/scripts/test_resolve.py

# The weekly Artificial Analysis ranking, against an invented page
python3 skills/orchestrator/scripts/test_aa_refresh.py

# The helper's routing, end to end through the orchestrator
skills/cmux/scripts/test-spawn-workspace.sh

# The session-note guard on close
skills/cmux/scripts/test-close-workspace.sh

# Yesterday's sessions, read from your own transcripts
python3 skills/recall/scripts/recall-day.py list yesterday --all-projects

# The graph renderer's own suite
python3 skills/graph/scripts/selftest.py

# Validate every skill in the repository
for d in skills/*/; do skills/skill-manager/scripts/validate.sh "$d"; done
```

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

A WARN from the validator is advice and a FAIL blocks. Most skills here warn
that `SKILL.md` is longer than 100 lines, which the validator allows for
skills that route to several workflows.

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
