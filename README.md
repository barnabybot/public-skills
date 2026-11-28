# public-skills

**Agentic engineering for knowledge workers on the command line.**

These skills are for people whose output is analysis, research, writing and
presentations, and who run AI agents in a terminal or desktop harness to produce
it. You use Claude Code, Codex, T3 Code or another CLI agent already, or you are
about to. You want several agents working on one goal, each starting from the
right context.

The repository holds ten skills, a [global contract](home/global.md) and a
[Home Repo map](AGENTS.md), taken from a working setup and rewritten so they run
on somebody else's machine.

Download individual skills or the complete collection as ZIP files at
[barnabyrobson.org/downloads](https://barnabyrobson.org/downloads/). The page
includes installation guidance. This repository holds the source; each download
links to the source commit used to build it.

## Operating principles

Seven structural choices shape this repository and the Home Repo layout behind
it:

1. **Keep an open harness across model providers and SDKs.** Every model vendor
   ships its own instruction filename and skills folder. Store skills and rules
   once in Git and symlink them into every tool's path (`~/.agents/skills/`,
   `~/.claude/skills/`, `~/.codex/skills/`, `~/.cursor/skills/`, plus
   `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`) so switching hosts or models costs
   nothing.
2. **Sync across devices.** Keep your Home Repo in Git and your Markdown vaults
   in a synced folder so every machine reads the same instructions, skills and
   session history.
3. **Separate personal and work, and bridge what is portable.** Run a separate
   Home Repo on a work laptop so client or employer material never touches
   personal storage. Keep generic, non-confidential skills in a portable
   repository (this repo or your own fork) that both setups can link cleanly.
4. **Separate Git repositories, vaults and scratch.** Code and skills live under
   `~/Repos/`. Knowledge vaults live under `$VAULTS_ROOT` (for example
   `~/Obsidian/`). Iterative renders live under `~/Scratch/YYYY-MM-DD/`. Never
   nest a Git repository inside a synced vault or scatter project folders on the
   Desktop.
5. **Give every vault a clear boundary.** Split personal knowledge, time-bounded
   projects, continuing operations, compiled wikis and agent runtime memory.
   Apply the Boundary Rule (confidential material stays inside its vault) and
   the Leaving Test (any work or project vault still makes sense without your
   personal Home Repo).
6. **Convert source material into clean Markdown.** PDFs, slide decks,
   spreadsheets and web pages are slow and noisy for agents to re-parse. Convert
   recurring inputs into clean Markdown once (or clean HTML where layout
   matters) and keep raw originals intact in `raw/`.
7. **Cut clutter and enforce ceilings in code.** Keep every `SKILL.md` at or
   under 100 lines with detail pushed into `references/` and `workflows/`, and
   enforce hygiene with validators and pre-commit ratchets instead of longer
   prose reminders.

## Context engineering

An agent's output is only as good as the context it starts with. These skills
give every kind of context one home, and they decide which agent reads it.

| Layer | Where it lives | What it holds |
|---|---|---|
| Instructions | `AGENTS.md` (with `CLAUDE.md` and `GEMINI.md` symlinks where needed) at each repo and vault root | How an agent works in that place: where files go, what it must not touch, how it writes |
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
past sessions from session notes and the transcripts your tools already write.

## Multi-agent work

One coordinator divides a multi-item goal into jobs while `model-routing`
selects each worker's model, effort, host payload and circuit-breaker fallback.
`orchestrator` is explicit-only and supports T3 Code, cmux and CLI subagents.
Its [host guide](skills/orchestrator/references/hosts.md) maps native tools,
worktree isolation and handoff. The optional `cmux` skill controls cmux
workspaces.

Here a Claude orchestrator coordinates Codex and Grok workers on a demo
project, each in its own pane, and reports a gap one worker left:

![cmux workspace with a Claude orchestrator and Codex and Grok workers](skills/orchestrator/assets/preview.png)

| Skill | Its part |
|---|---|
| [`vault-setup`](skills/vault-setup/) | Creates each vault type with its folder tree, templates and instruction file |
| [`recall`](skills/recall/) | Finds past work in session notes where available, with native transcripts for missing detail or a setup without notes |
| [`session-intelligence`](skills/session-intelligence/) | Mines multi-runtime agent traces (Claude Code, Codex, Grok, Muse, Antigravity) and `$AGENT_NOTES` session notes into an interactive automation roadmap (`index.html`) and behavioural portrait (`life.html`) with period filtering and verbatim quote verification |
| [`model-routing`](skills/model-routing/) | Routes tasks to the best eligible model across T3 Code, cmux and CLI using Python stdlib only, with provider circuit breakers and automated 2-hop takeovers |
| [`orchestrator`](skills/orchestrator/) | Explicit-only coordinator for multi-item queues, multi-repo work, parallel fan-outs and session handoffs across T3 Code, cmux and CLI. Calls `model-routing` for preflight and takeover |
| [`cmux`](skills/cmux/) | Controls workspaces and browser panes in the optional cmux terminal application. Calls `model-routing` for routing policy |
| [`graph`](skills/graph/) | Renders a programme of work as an interactive dependency graph with dependency tracing, foldable branches, node inspection and a read-only `--frontier` CLI for agent drain loops. Marks a node stale when its inputs change after its output was built |
| [`editorial-review`](skills/editorial-review/) | Checks prose and argument before it goes to a reader, including the tells that mark machine-written text |
| [`skill-manager`](skills/skill-manager/) | Writes and reviews new skills: description rules, a pre-ship checklist, a validator and a portable multi-runtime whole-tree audit |
| [`hygiene`](skills/hygiene/) | Runs post-event and weekly repository hygiene sweeps across Git hooks, binary ratchets, code-comment burn-downs and ADRs, 150-run CI audits, architecture debt triage, and agent safety and blast-radius audits |

`graph` turns one YAML state file into a page like this. Inspect nodes, filter
the DAG and expand the folded content-audit branch. The design-brief node reads
stale because its input changed after it was built
([source](skills/graph/assets/demo.state.yaml)):

![graph render of a sample website relaunch](skills/graph/assets/preview.png)

[home/global.md](home/global.md) supplies global steering.
[AGENTS.md](AGENTS.md) maps the Home Repo, shared skills and destinations.
Each project or vault has its own `AGENTS.md` for local instructions.

## Where these run

An agent is a model plus an agent runtime. These skills are written for the
runtime: an agent CLI such as Claude Code or Codex reads a `SKILL.md` and
follows it. The runtime can run in several places, and the skills load the same
way in each.

| Where | Examples | Notes |
|---|---|---|
| A terminal | macOS Terminal, Windows Terminal | Shared skills and supported CLI subagents; cmux control requires cmux |
| A terminal workspace | cmux | Every skill. CLIs from several providers run side by side, and one agent can start, read and close the others |
| An editor or harness | T3 Code, VS Code, Cursor | Run Claude Code, Codex or other providers under one shell. Symlink both `~/.agents/skills/` and provider folders so every harness sees the same skills and `AGENTS.md` |
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
     install steps below cover `~/.agents/skills/`, Claude Code, Codex and
     Cursor; another CLI reads a `SKILL.md` as plain instructions. The cmux
     helper launches Claude Code, Codex and Grok.
   - [Obsidian](https://obsidian.md), where you read what your agents write.
     Any Markdown editor works.
3. **Open your chosen host, start the agent and sign in.**
4. **Paste this prompt:**

   ```
   Read README.md, AGENTS.md and home/global.md in public-skills.
   Tell me what each skill does and what you would install, then wait for my go.
   After I say go:
   1. Clone the repo to ~/Repos/public-skills and link every skill into my
      active skills folders (~/.agents/skills, ~/.claude/skills, ~/.codex/skills
      or ~/.cursor/skills as installed).
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
- **`session-intelligence` runs on Python 3 stdlib only.** It discovers local
  transcripts across Claude Code, Codex, Grok, Muse and Antigravity plus
  `$AGENT_NOTES/Sessions/*.md` notes (and optional `$AGENT_NOTES/Cron/sessions/*.md`
  logs), verifies quotes deterministically, and renders self-contained HTML apps
  using your local CLI runtime or `run_workflow`.
- **Three skills need nothing beyond Python stdlib or Bash.** `vault-setup`,
  `editorial-review` and `hygiene` run anywhere (`gh` optional for remote CI
  audits in `hygiene`).
- **`model-routing` and `orchestrator` use Python stdlib only.**
  `model-routing` owns the JSON routing catalogue (`references/routing-catalog.json`),
  host adapters (`--host t3 | cmux | cli`), circuit breaker and 2-hop takeover
  with zero `PyYAML` dependency. `orchestrator` is explicit-only and delegates
  routing decisions to `model-routing`. Install `cmux` only for cmux workspace
  dispatch.
- **Only `graph` needs PyYAML**
  (`python3 -m pip install --user PyYAML`). Apart from `recall`'s optional graph
  mode (`networkx` and `pyvis`), it is the only non-stdlib dependency in the
  repository.
- **`skill-manager` runs across runtimes.** `validate.sh` needs only Bash.
  `scripts/skill_audit.py` runs the whole-tree audit portably across `agy`,
  `claude`, `codex`, `grok` or `muse` (and `workflows/skill-audit.workflow`
  runs in hosts with `run_workflow`).
- **The routing catalogue is a placeholder.** In `skills/model-routing/`,
  `provider_a` resolves to sample IDs and `provider_b` resolves to deliberately
  invalid IDs, so an unconfigured second provider fails loudly instead of
  launching the wrong model. Edit `SKILL.md` and `references/routing-catalog.json`
  before you dispatch work you care about.

## Where things get written

Three of the skills write session notes and handoff briefs. They agree on one
root, set by one environment variable. Point it at the root of your agents vault
in `~/.zshenv` so that every shell your agents start can read it:

```bash
export AGENT_NOTES="$HOME/Obsidian/Agents"  # unset, it falls back to ~/agent-notes
```

| Path | Holds |
|---|---|
| `$AGENT_NOTES/Sessions/` | One note per session, `YYYY-MM-DD <slug>.md`, with `agent:`, `host:`, `model:`, `effort:` and `status:` in the frontmatter |
| `$AGENT_NOTES/Sessions/Handoffs/` | Handoff briefs, one per handoff |

The folders are created on first use. An agents vault made by `vault-setup`
already has `Sessions/`, `Sessions/Handoffs/` and `Ops/` at its root, so its
root is the right value.

## Install

A skill is a folder with a `SKILL.md` in it. Clone the repository once under
`~/Repos/public-skills`, then symlink each skill folder into every runtime you
use. Each runtime reads the `description:` line to decide when a skill applies.

```bash
mkdir -p ~/Repos
git clone https://github.com/barnabybot/public-skills.git ~/Repos/public-skills
```

| Runtime | Global skills folder |
|---|---|
| T3 Code, Codex, Antigravity and Agent Skills hosts | `~/.agents/skills/` |
| Claude Code | `~/.claude/skills/` |
| Codex CLI (legacy path) | `~/.codex/skills/` |
| Cursor | `~/.cursor/skills/` |

Link all ten skills into each target you use, leaving any existing skill with
the same name untouched:

```bash
for target in ~/.agents/skills ~/.claude/skills ~/.codex/skills ~/.cursor/skills; do
  mkdir -p "$target"
  for d in ~/Repos/public-skills/skills/*/; do
    n=$(basename "$d")
    [ -e "$target/$n" ] && echo "skip $target/$n: already installed" || ln -s "$d" "$target/$n"
  done
done
```

Keep only the folders for runtimes you actually run, or link all four so a new
harness picks up your skills on first launch. Restart your agent, then type
`/recall` to check it loaded. Project-scoped instead of global? Use
`.agents/skills/` inside the project and link `.claude/skills/` and
`.cursor/skills/` to it with relative symlinks.

For Codex CLI, set `default_mode_request_user_input = true` under `[features]`
in `~/.codex/config.toml` so skills can present intake questions through Codex's
native `request_user_input` menu.

**Another runtime.** A `SKILL.md` is Markdown with YAML frontmatter, so most of
these read as plain instructions. Paste the file into your system prompt, or
point your tool at the folder. `orchestrator` and `cmux` are the two that need
real scripts on disk.

## Adopt the Home Repo split

This repository supports two instruction layouts. Pick the one that fits your
setup:

- **Split layout (shipped here).** Keep global rules in
  [home/global.md](home/global.md) and your repository, project and vault map in
  root [AGENTS.md](AGENTS.md). Symlink `home/global.md` into each global tool
  location.
- **Unified layout.** Merge global steering and the workspace map into one root
  `AGENTS.md` in your private Home Repo, symlink root `CLAUDE.md` and
  `GEMINI.md` to `AGENTS.md`, and symlink that single file into each global tool
  location. Some multi-provider harnesses read only one filename per provider,
  so linking all three names prevents silent instruction misses.

Review existing global instructions and merge your rules before replacing a
link. Create the tool folders first, then use absolute paths for these links:

```sh
ln -s <your-home-repo>/home/global.md ~/.claude/CLAUDE.md
ln -s <your-home-repo>/home/global.md ~/.codex/AGENTS.md
ln -s <your-home-repo>/home/global.md ~/.gemini/GEMINI.md
```

Optional version-controlled `home/harness/` templates may sit beside
`home/global.md` (for example `claude-settings.json` and `codex-config.toml`).
Merge shared keys declaratively into live tool config files rather than
overwriting machine-local state, and keep secrets outside the repository.

**Personal and work setups.** If you run agents on a work laptop, create a
separate work Home Repo with its own `AGENTS.md` and vaults. Clone
`public-skills` (or your own scrubbed fork of portable skills) alongside it and
link only the skills you want into your work machine's `~/.agents/skills/` and
provider folders. Personal vaults, private workflows and client material stay
strictly separated.

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
# Validate every skill in the repository
./.agents/skills/verify-public-skills/scripts/validate-all

# The routing table resolves, and no workspace is spawned
skills/cmux/scripts/spawn-workspace.sh test --tier systems --dry-run

# The routing catalogue and SKILL.md table are structurally valid
python3 skills/model-routing/scripts/check.py --no-live --no-log

# The model-routing preflight, circuit-breaker and takeover test suite
python3 -m unittest discover -s skills/model-routing/scripts -p 'test_*.py'

# The portable skill-audit test suite
python3 -m unittest discover -s skills/skill-manager/scripts/tests -p 'test_*.py'

# The session-intelligence discovery, rendering and friction test suites
python3 -m unittest discover -s skills/session-intelligence/scripts/tests -p 'test_*.py'

# Yesterday's sessions, read from your own transcripts
python3 skills/recall/scripts/recall-day.py list yesterday --all-projects

# The graph renderer's own suite
python3 skills/graph/scripts/selftest.py

# Binary and comment-hygiene ratchets
python3 scripts/check_binary_ratchet.py --repo .
python3 scripts/check_code_comments.py --root . --ratchet
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

A WARN from the validator is advice and a FAIL blocks. Every `SKILL.md` in this
repository stays at or under 100 lines, pushing deeper rules and examples into
`references/` and `workflows/`.

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
