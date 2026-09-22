---
name: cmux
version: 1.0.0
description: >-
  Manage cmux workspaces and browser panes. Use for spawn, spin up, dispatch, restore sessions, cmux status, workspace screens or opening local HTML in the cmux browser.
fallback: If cmux is unavailable, write the prompt or handoff file under $AGENT_NOTES/Sessions/Handoffs/ and tell the user the workspace could not be opened.
---

# cmux

Manage cmux workspaces and the coding agents running inside them from one
terminal.

> For the multi-agent **orchestrator** pattern - one agent spawns and
> coordinates many through session notes - use the `orchestrator` skill. This
> skill covers the raw mechanics.

**Requires** [cmux](https://www.cmux.dev) on the `PATH`, and the **orchestrator**
skill installed beside this one, because `spawn-workspace.sh` routes through its
resolver. Everything else below is cmux CLI plus the two helper scripts in this
directory.

## Configuration

One environment variable. Set it in your shell profile, or leave it and take the
default.

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/`, handoff briefs in `Sessions/Handoffs/` |

`spawn-workspace.sh` creates `$AGENT_NOTES` on first use, so a fresh install
needs no setup. Point it at a folder in a notes vault if you keep one - the
scripts care only that the folder exists and that they may write to it.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/spawn-workspace.sh` | Spawn a named workspace with no focus steal. Routes the seat through the **orchestrator** skill's resolver (`--tier <letter>`), sets effort on the launched CLI, and writes the session note with model, effort and the route log. The canonical helper. |
| `scripts/test-spawn-workspace.sh` | Dry-run fixture test for the helper's routing. Nothing is spawned. Run it after any edit to `spawn-workspace.sh`, or to the orchestrator's table, metadata or resolver. |
| `scripts/close-workspace.sh` | Close a workspace AND flip its session note to `status: done` with an `ended:` stamp. Flips only a note still open. cmux reuses workspace numbers, so closed notes on the same id are reported and left alone. Use this instead of raw `cmux close-workspace`. |
| `scripts/test-close-workspace.sh` | Fixture test for that guard. Run it after any edit to `close-workspace.sh`. |
| `scripts/cmux-session-map.py` | Optional `SessionStart` / `SessionEnd` hook. Maps Claude Code sessions to cmux surfaces in `/tmp/cmux-session-map.json`. Save it to `~/.claude/hooks/` and register it if you want session-to-surface tracking. |

`scripts/spawn-workspace.sh --help` prints the header comment block and exits. A
first argument beginning with `-` is refused: before that check an unknown flag
became the workspace name and spawned a live seat.

Reference docs:

- `references/pitfalls.md` - failure modes that bit real sessions
  (window-scoping, multi-line send, current-workspace drift, shared-branch
  commits).
- the **orchestrator** skill's `references/routing-rules.md` - how a request
  becomes a tier letter, and what the route log is for.

## Runtime and permission mode

`spawn-workspace.sh` launches `claude --dangerously-skip-permissions`, `codex
--yolo` or `grok --always-approve`, with the resolved effort on the command
line. Under `--tier` the routing row decides the runtime. `--agent` matters only
with an explicit `--model` whose id the table does not know, and otherwise
defaults to the parent runtime detected from the environment
(`CMUX_AGENT_LAUNCH_KIND`, then `CLAUDECODE=1` for claude, then the script
path). The matching `agent:` value goes into the session note.

Do not strip the yolo or skip-permissions flags. A spawned agent that blocks on
every tool call defeats the whole workflow. Where a workspace needs a human in
the loop, put checkpoints in the prompt instead.

## Model selection

`spawn-workspace.sh --tier <letter>` resolves agent, model and effort by calling
the **orchestrator** skill's `scripts/resolve.py`, which reads the marked table
in that skill's `SKILL.md`. The tiering rule is in its
`references/routing-rules.md`. `--model` with `--effort` bypasses
the resolver, for successors and for models named in the request. A call with
neither `--tier` nor `--model` is refused, and the usage text lists the tiers.

**Aliases float.** `sonnet` and `opus` re-resolve to whatever the current
generation ships. The table pins ids, and a successor of a live lineage passes
the predecessor's `--model` and `--effort` explicitly so an upgrade never lands
mid-lineage.

**Routing lives in the orchestrator skill, and not here.** The seat that
dispatches keeps the dispatch policy, so the table, the tiering rule and the
resolver sit together in one package. This helper reads them; it does not own
them. Install both skills, or `--tier` has nothing to resolve against.

The shipped table is a placeholder marked `basis: practice`, which means
unmeasured. Edit the orchestrator's table and
`references/routing-metadata.yaml`, then let the route logs tell you which rows
earn their seat.

## Quick reference

```bash
# List workspaces (window-scoped - see references/pitfalls.md)
cmux list-workspaces

# Spawn a named workspace with a prompt; the tier is required
scripts/spawn-workspace.sh "workspace-name" --tier C --prompt "Your prompt here"

# Project-specific cwd
scripts/spawn-workspace.sh "workspace-name" --tier C --cwd "$HOME/code/repo" --prompt "..."

# New window instead of the caller's window
scripts/spawn-workspace.sh "workspace-name" --tier C --prompt "..." --new-window

# Long handoff prompt - store it as a file first
scripts/spawn-workspace.sh "workspace-name" --tier F \
  --prompt-file "$AGENT_NOTES/Sessions/Handoffs/2026-09-22 topic handoff.md"

# Hard investigation - tier E, with the word that decided the tier
scripts/spawn-workspace.sh "workspace-name" --tier E --reason "prior pass found no cause" \
  --prompt-file "$AGENT_NOTES/Sessions/Handoffs/2026-09-22 topic handoff.md"

# A named model, bypassing the table (successors, and models the user names)
scripts/spawn-workspace.sh "workspace-name" --model claude-opus-5 --effort medium --prompt "..."

# See the route without spawning
scripts/spawn-workspace.sh "workspace-name" --tier E --dry-run

# Rename / select
cmux rename-workspace --workspace workspace:N "Name"
cmux select-workspace --workspace workspace:N

# Close - flips the matching session note to status: done
scripts/close-workspace.sh workspace:N
# (Raw `cmux close-workspace --workspace workspace:N` leaves the note stuck in-progress.)
```

## Open local HTML in the cmux browser

When the user asks for the **cmux browser**, use cmux's native browser pane.
Keep the file in the caller's current workspace and focus the new split:

```bash
cmux browser status
cmux browser open 'file:///absolute/path/report%20name.html' --focus true
# Read surface:S from the output, then verify the loaded page:
cmux browser --surface surface:S wait --load-state complete --timeout-ms 10000
cmux browser --surface surface:S get title
cmux browser --surface surface:S get url
```

Encode spaces as `%20`. A successful open reports `OK surface=surface:S
pane=pane:M placement=split`; confirm the title and the `file://` URL before
reporting completion. Do not substitute Chrome or another browser surface when
the user names cmux.

## Open Markdown in a cmux viewer

`cmux markdown open /abs/path/file.md --workspace workspace:N --focus false`
renders the file in a viewer surface that reloads on disk changes. It takes
`--surface` (the surface to split from) and no `--pane`. `read-screen` cannot
read a viewer surface and a browser screenshot cannot capture it, so confirm
rendering with the user. Replacing the document in a viewer pane works only as
close-then-open: `close-surface` the old viewer, then open the new file.

## Sidebar status for a worker

Three verbs write to a workspace's sidebar, so a worker's progress is visible
without a `read-screen`:

```bash
cmux set-status build "compiling" --icon hammer --color "#ff9500" --workspace workspace:N
cmux set-progress 0.5 --label "6 of 12 recipes" --workspace workspace:N
cmux log --level success --source test "all 42 pass" --workspace workspace:N
```

The key on `set-status` is per tool; reuse it to update the pill. `cmux
surface-health --workspace workspace:N` lists surface state when a relay target
may be stale.

## Key patterns

- **Name every active agent workspace.** Use `Orchestrator - <task>` for the
  coordinator and `Worker - <task>` for executors. After spawning or taking over
  workspaces, list them, replace generic titles, and check each final name
  against its workspace id.
- **Send a message to another workspace - the five-step relay.** Every cmux verb
  returns `OK` for a state one step short of delivery, so the target's own
  screen is the only evidence the message arrived. Run the clear, the send and
  the submit as one shell command, then read the screen:

  ```bash
  CMUX_QUIET=1 cmux send-key --workspace workspace:N Escape \
    && CMUX_QUIET=1 cmux send --workspace workspace:N "one line, or a pointer to a file" \
    && CMUX_QUIET=1 cmux send-key --workspace workspace:N Enter
  CMUX_QUIET=1 cmux read-screen --workspace workspace:N --lines 20
  ```

  - **Keep every payload to one line.** `cmux send` writes into an interactive
    composer where each newline submits the line before it, so a multi-line
    commit message, report or brief fragments and arrives garbled. Write
    anything longer than a sentence to a file and send the pointer: `Read
    /tmp/<name>.md in full and follow it.` Durable briefs go under
    `$AGENT_NOTES/Sessions/Handoffs/`, short mid-flight relays under `/tmp`.
  - **`--workspace` is a flag. No cmux verb accepts a positional workspace.**
    `cmux send workspace:N "text"` delivers to your *own* workspace with the ref
    swallowed into the message body and still prints `OK`. `cmux read-screen
    workspace:6` fails with `unexpected arguments`.
  - **Escape first.** `send` appends to any unsent draft sitting in the target
    composer, so a leftover line is submitted in front of your message.
  - **Enter belongs in the same shell command.** `send` stages text and
    `send-key Enter` submits it, and both print the same `OK` line. A `send`
    reply on its own is an incomplete relay.
  - **Check the replies against the screen.** Confirm `workspace:N` in each `OK
    surface:S workspace:N` reply equals your intended target, and confirm your
    own text on the target's screen before you report the message delivered.
- **Read any agent's screen:** `cmux read-screen --workspace workspace:N`
- **Prompt files:** durable handoff prompts belong in
  `$AGENT_NOTES/Sessions/Handoffs/`. Use `/tmp` only for short mid-flight `cmux
  send` workarounds. Never use the Desktop for session history or handoffs.

## Surface (tab) management

```bash
cmux list-panes --workspace workspace:N
cmux list-pane-surfaces --workspace workspace:N
cmux move-surface --surface surface:S --workspace workspace:N
cmux reorder-surface --surface surface:S --index 0
cmux rename-tab --surface surface:S "New Name"
cmux close-surface --surface surface:S --workspace workspace:N
cmux drag-surface-to-split --surface surface:S left|right|up|down
cmux break-pane --workspace workspace:N --pane pane:M
```

## Socket API

Programmatic control through a Unix socket at `/tmp/cmux.sock`. Request format:
newline-terminated JSON. Methods: `workspace.list`, `workspace.create`,
`workspace.select`, `surface.send_text`, `surface.send_key`, `set-status`,
`set-progress`, `notification.create`. CLI flags: `--json`, `--workspace ID`,
`--surface ID`, `--id-format refs|uuids|both`. Docs:
https://www.cmux.dev/docs/api
