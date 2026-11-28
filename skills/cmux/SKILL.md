---
name: cmux
version: 1.3.0
description: >-
  Control workspaces and browser panes in the optional cmux terminal application. Use for spawn, spin up, dispatch, restore sessions, cmux status, workspace screens or opening local HTML in the cmux browser.
fallback: If cmux is unavailable, write the prompt or handoff file under $AGENT_NOTES/Sessions/Handoffs/ and tell the user the workspace could not be opened.
---

# cmux

Manage cmux workspaces and the coding agents running inside them from one
terminal.

> For the multi-agent **orchestrator** pattern - one agent spawns and
> coordinates many through session notes - use the `orchestrator` skill. This
> standalone host driver covers cmux mechanics and calls `model-routing` for routing policy.

**Requires** [cmux](https://www.cmux.dev) on the `PATH`, and the **model-routing**
skill installed beside this one, because `spawn-workspace.sh` routes through its
stdlib resolver. Everything else below is cmux CLI plus the helper scripts in this
directory.

## Verification

Run the shell guards and discovered Python suite. Run hyphenated test files
directly because unittest discovery skips them.

```sh
bash scripts/test-spawn-workspace.sh
bash scripts/test-close-workspace.sh
python3 -m unittest discover -s scripts -p 'test*.py'
python3 scripts/test-group-header.py
python3 scripts/test-close-idle-codex.py
```

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
| `scripts/spawn-workspace.sh` | Spawn a named workspace with no focus steal. Routes the seat through the **orchestrator** skill's resolver (`--tier <category>`), accepts `--request` so an unauthorised or unread provider exits 3 before a workspace exists, stamps the surface for a later cross-model handoff, and writes the session note with model, effort and the route log. `--route-out` / `--resolved-route` reuse one fresh resolution. The canonical helper. |
| `scripts/group_header.py` | Keep a permanent blank group header. `ensure` creates or repairs the plain-shell anchor. `before-close` returns `retained-header` for that anchor so close and idle-exit leave it in place. |
| `scripts/stamp_surface.py` | Write the launched agent, model, effort and directory for the new surface. Spawn runs it before the agent. The orchestrator reads the stamp on a cross-model handoff. |
| `scripts/test_spawn_launch.py` | Launch fixtures for Claude, Codex and Grok, unsupported-runtime refusal, and absence of trust screen reads or key presses. |
| `scripts/test-spawn-workspace.sh` | Dry-run fixture test for the helper's routing. Nothing is spawned. Run it after any edit to `spawn-workspace.sh`, or to the orchestrator's table, metadata or resolver. |
| `scripts/test-spawn-group.sh` | Fixture check for group inheritance, handoff prompts, focus preservation and creation errors. Runs without live workspaces. |
| `scripts/close-workspace.sh` | Close a workspace AND flip its session note to `status: done` with an `ended:` stamp. Flips only a note still open. cmux reuses workspace numbers, so closed notes on the same id are reported and left alone. `--exit-idle-codex` retires a finished idle Codex terminal by normal `ctrl+d`. Use this instead of raw `cmux close-workspace`. |
| `scripts/idle_codex.py` | Prove whether a Codex seat is idle from the hook store (`codex-hook-sessions.json`) and screen footer grammar (`scripts/fixtures/idle-footer.json`). |
| `scripts/relay-codex.py` | Send a message to a live Codex seat through its verified direct session queue (`codex queue`) without touching the terminal input box. |
| `scripts/test-close-workspace.sh` | Fixture test for that guard. Run it after any edit to `close-workspace.sh`. |
| `scripts/test-close-idle-codex.py` | Fixture test for `--exit-idle-codex`. |
| `scripts/test_idle_codex.py` | Unit tests for `idle_codex.py`. |
| `scripts/test_relay_codex.py` | Unit tests for `relay-codex.py`. |
| `scripts/cmux-session-map.py` | Optional `SessionStart` / `SessionEnd` hook. Maps Claude Code sessions to cmux surfaces in `/tmp/cmux-session-map.json`. Save it to `~/.claude/hooks/` and register it if you want session-to-surface tracking. |

`scripts/spawn-workspace.sh --help` prints the header comment block and exits. A
first argument beginning with `-` is refused: before that check an unknown flag
became the workspace name and spawned a live seat.

Reference docs:

- `references/pitfalls.md` - failure modes that bit real sessions
  (window-scoping, multi-line send, current-workspace drift, shared-branch
  commits).
- the **model-routing** skill's `references/routing-rules.md` - how a request
  becomes a category, and how preflight, circuit breakers and takeovers work.

- `references/operations.md` - idle Codex retirement (`--exit-idle-codex`), runtime and permission flags, model selection, command quick reference, browser pane, viewer mode, sidebar status, surfaces and socket API.
