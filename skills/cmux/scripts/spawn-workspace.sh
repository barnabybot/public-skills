#!/bin/bash
# Spawn a named cmux workspace with Claude Code, Codex or Grok (no focus steal).
#
# Usage:
#   spawn-workspace.sh <name> (--tier <letter> | --model <id> [--effort <level>]) [--agent codex|claude|grok] [--of <letter>] [--builder <model-id>] [--reason "..."] [--cwd <path>] [--worktree [branch]] [--prompt "..."] [--prompt-file <path>] [--goal "..."] [--session] [--no-session] [--same-window] [--new-window] [--dry-run]
#
# By default a session note is created in $AGENT_NOTES/Sessions/
# ($AGENT_NOTES defaults to ~/agent-notes). Pass --no-session to skip.
#
# --agent         Runtime to launch: codex, claude or grok. With --tier the
#                 routing row decides and this flag is ignored. Defaults to the
#                 parent runtime detected from the environment:
#                 CMUX_AGENT_LAUNCH_KIND, then CLAUDECODE=1 (claude), then the
#                 script path.
# --tier          Routing tier: O A B C D E F V, and R with --of and --builder.
#                 Resolved by the orchestrator skill's scripts/resolve.py against
#                 the marked table in its SKILL.md. A call with neither --tier nor
#                 --model is refused before any cmux call. The tiering rule - how a
#                 request becomes a letter - is in the orchestrator skill's
#                 references/routing-rules.md.
# --of            With --tier R: the tier of the work under review.
# --builder       With --tier R: the model id that built the work; it is excluded.
# --reason        Why this tier. Written into the route log on the session note.
# --model         Explicit model id, passed to the child CLI. Bypasses the table,
#                 for successors and for models named in the request.
# --effort        Effort level passed to the child CLI: claude --effort, codex
#                 -c model_reasoning_effort=, grok --reasoning-effort. Also
#                 prepended to the prompt as its first line, `Effort: <level>`.
# --dry-run       Resolve the route, print the route line and the launch command,
#                 exit 0. Nothing is spawned, no worktree or note is written.
# --cwd           Working directory for the launched agent. Defaults to
#                 $AGENT_NOTES so new workspaces do not inherit the caller's
#                 current directory.
# --worktree [br] Give the agent its own git worktree instead of sharing --cwd.
#                 Requires --cwd inside a git repo. Creates
#                 <repo-parent>/<repo>-wt/<workspace-slug> and points the agent
#                 there. Pass a branch name to check out an existing branch;
#                 omit it to create one named after the workspace.
#                 Use this for ANY agent that will edit a repo other sessions
#                 also touch. A shared working tree is single-writer: one
#                 session's `git checkout` silently rewrites every other
#                 session's files.
#                 Caveat: a branch can live in only one worktree at a time, so
#                 worktree work needs deliberate commits.
# --prompt        Initial prompt passed to the agent in the new workspace.
# --prompt-file   Path to a file whose contents become the launch prompt
#                 (preferred for long or multi-line prompts).
# --goal          Goal line written into the session note (defaults to prompt).
# --same-window   Keep the workspace in the current cmux window (the default).
# --new-window    Open a new cmux window for this workspace.

set -e

USAGE='Usage: spawn-workspace.sh <name> (--tier <letter> | --model <id> [--effort <level>]) [--agent codex|claude|grok] [--of <letter>] [--builder <model-id>] [--reason "..."] [--cwd <path>] [--worktree [branch]] [--prompt "..."] [--prompt-file <path>] [--goal "..."] [--session] [--no-session] [--same-window] [--new-window] [--dry-run]'

# The routing canon and its resolver, found from this script's real path so a
# copy reads its own canon. ROUTING_RESOLVER overrides for tests.
# readlink -f needs coreutils on older macOS; fall back to the plain path.
SCRIPT_REAL="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
# The orchestrator package owns the routing table, the rule and the resolver.
# Found relative to this script's real path, so a copy reads its own sibling.
RESOLVER="${ROUTING_RESOLVER:-$(cd "$(dirname "$SCRIPT_REAL")/../../orchestrator/scripts" 2>/dev/null && pwd)/resolve.py}"
PYTHON="${SPAWN_PYTHON:-python3}"

# Where session notes and handoff briefs live. One root, set it to your own.
AGENT_NOTES="${AGENT_NOTES:-$HOME/agent-notes}"

# The name is taken positionally and the flag loop below never sees it, so
# without these two checks any unknown first argument becomes a workspace name
# and spawns a live agent plus a session note. `--help` did exactly that once.
# Both checks run before any cmux call.
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
  exit 0
fi

if [[ "${1:-}" == -* ]]; then
  echo "The first argument is the workspace name, and '$1' begins with a dash." >&2
  echo "$USAGE" >&2
  exit 2
fi

NAME="${1:?$USAGE}"
shift

PROMPT=""
GOAL=""
WRITE_SESSION=1
OPEN_NEW_WINDOW=0
AGENT=""
TIER=""
MODEL=""
EFFORT=""
OF=""
BUILDER=""
REASON=""
DRY_RUN=0
WORKDIR="$AGENT_NOTES"

# Parent-runtime detection. Prefer env signals over the script path, because
# ~/.codex/skills and ~/.claude/skills often symlink to the same checkout and
# the path would then always resolve to one of them.
if [[ -n "$CMUX_AGENT_LAUNCH_KIND" ]]; then
  case "$CMUX_AGENT_LAUNCH_KIND" in
    claude|codex|grok) AGENT="$CMUX_AGENT_LAUNCH_KIND" ;;
  esac
fi
if [[ -z "$AGENT" && "$CLAUDECODE" == "1" ]]; then
  AGENT="claude"
fi
if [[ -z "$AGENT" ]]; then
  case "$0" in
    *"/.codex/"*) AGENT="codex" ;;
    *) AGENT="claude" ;;
  esac
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      case "$2" in
        codex|claude|grok) AGENT="$2"; shift 2 ;;
        *) echo "Unknown agent: $2 (expected codex, claude or grok)" >&2; exit 1 ;;
      esac
      ;;
    --tier) TIER="$2"; shift 2 ;;
    --of) OF="$2"; shift 2 ;;
    --builder) BUILDER="$2"; shift 2 ;;
    --reason) REASON="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --effort) EFFORT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --cwd) WORKDIR="${2/#\~/$HOME}"; shift 2 ;;
    --worktree)
      USE_WORKTREE=1
      if [[ -n "${2:-}" ]] && [[ "$2" != --* ]]; then
        WORKTREE_BRANCH="$2"; shift 2
      else
        shift
      fi
      ;;
    --prompt) PROMPT="$2"; shift 2 ;;
    --prompt-file)
      if [[ ! -f "$2" ]]; then echo "prompt-file not found: $2" >&2; exit 1; fi
      PROMPT="$(cat "$2")"
      shift 2
      ;;
    --goal) GOAL="$2"; shift 2 ;;
    --session) WRITE_SESSION=1; shift ;;
    --no-session) WRITE_SESSION=0; shift ;;
    --new-window) OPEN_NEW_WINDOW=1; shift ;;
    --same-window) OPEN_NEW_WINDOW=0; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# The notes root is created on demand so a fresh install works with no setup.
# Any other cwd must already exist, because a typo should not silently make one.
if [[ ! -d "$WORKDIR" ]]; then
  if [[ "$WORKDIR" == "$AGENT_NOTES" ]]; then
    mkdir -p "$WORKDIR"
  else
    echo "cwd not found: $WORKDIR" >&2
    exit 1
  fi
fi

# Route before anything is created. A bare call is refused: the tier is the one
# routing decision the caller owns, and the usage text carries the tiers.
if [[ -z "$MODEL" && -z "$TIER" ]]; then
  echo "Pass --tier <letter>, or --model <id> with --effort <level>. Tiers:" >&2
  "$PYTHON" "$RESOLVER" --list-tiers >&2 || true
  echo "$USAGE" >&2
  exit 2
fi
if [[ ! -f "$RESOLVER" ]]; then
  echo "routing resolver not found: $RESOLVER" >&2
  exit 1
fi
ROUTE_ARGS=()
if [[ -n "$MODEL" ]]; then
  ROUTE_ARGS=(--model "$MODEL")
  [[ -n "$EFFORT" ]] && ROUTE_ARGS+=(--effort "$EFFORT")
  [[ -n "$AGENT" ]] && ROUTE_ARGS+=(--agent "$AGENT")
  [[ -n "$TIER" ]] && ROUTE_ARGS+=(--tier "$TIER")
else
  ROUTE_ARGS=(--tier "$TIER")
  [[ -n "$OF" ]] && ROUTE_ARGS+=(--of "$OF")
  [[ -n "$BUILDER" ]] && ROUTE_ARGS+=(--builder "$BUILDER")
fi
[[ -n "$REASON" ]] && ROUTE_ARGS+=(--reason "$REASON")
set +e
ROUTE_OUT="$("$PYTHON" "$RESOLVER" "${ROUTE_ARGS[@]}")"
ROUTE_RC=$?
set -e
if [[ "$ROUTE_RC" -eq 3 ]]; then
  eval "$ROUTE_OUT"
  echo "A ruling is needed before this spawn (tier $ROUTE_TIER): $ROUTE_ASK" >&2
  echo "Ask, then spawn again with --model and --effort explicit." >&2
  exit 3
elif [[ "$ROUTE_RC" -ne 0 ]]; then
  echo "route resolution failed (exit $ROUTE_RC)" >&2
  exit "$ROUTE_RC"
fi
eval "$ROUTE_OUT"
if [[ -z "$MODEL" && -n "$AGENT" && "$AGENT" != "$ROUTE_AGENT" ]]; then
  echo "note: --agent $AGENT ignored; tier $ROUTE_TIER routes to $ROUTE_AGENT" >&2
fi
AGENT="$ROUTE_AGENT"
MODEL="$ROUTE_MODEL"
EFFORT="$ROUTE_EFFORT"
[[ "$EFFORT" == "unset" ]] && EFFORT=""
[[ -n "$ROUTE_LEGACY_NOTE" ]] && echo "deprecated: $ROUTE_LEGACY_NOTE" >&2

# The launch command. $MODEL is single-quoted: 1M-context ids look like
# `claude-opus-5[1m]`, and the brackets are glob metacharacters. Unquoted, zsh
# fails the whole command with "no matches found" and the agent never starts.
case "$AGENT" in
  codex)
    RUNNER="codex --yolo"
    [[ -n "$MODEL" ]] && RUNNER="$RUNNER --model '$MODEL'"
    [[ -n "$EFFORT" ]] && RUNNER="$RUNNER -c model_reasoning_effort='$EFFORT'"
    SESSION_AGENT="codex"
    ;;
  claude)
    RUNNER="claude --dangerously-skip-permissions"
    [[ -n "$MODEL" ]] && RUNNER="$RUNNER --model '$MODEL'"
    [[ -n "$EFFORT" ]] && RUNNER="$RUNNER --effort '$EFFORT'"
    SESSION_AGENT="claude-code"
    ;;
  grok)
    RUNNER="grok --always-approve"
    [[ -n "$MODEL" ]] && RUNNER="$RUNNER --model '$MODEL'"
    [[ -n "$EFFORT" ]] && RUNNER="$RUNNER --reasoning-effort '$EFFORT'"
    SESSION_AGENT="grok"
    ;;
esac

# The brief and the seat agree on effort by construction: the resolved level
# becomes the prompt's first line unless the caller already wrote one.
if [[ -n "$PROMPT" && -n "$EFFORT" ]] && ! printf '%s' "$PROMPT" | head -1 | grep -q '^Effort:'; then
  PROMPT="Effort: $EFFORT"$'\n\n'"$PROMPT"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry-run: workspace '$NAME' in $WORKDIR${USE_WORKTREE:+ (--worktree would add its own tree)}"
  echo "dry-run: exec $RUNNER"
  echo "dry-run: note agent=$SESSION_AGENT model=$ROUTE_MODEL_ID effort=${EFFORT:-unset}"
  echo "$ROUTE_LINE"
  exit 0
fi

# --worktree: hand the agent its own tree so a concurrent session's checkout
# cannot rewrite its files mid-task.
if [[ "${USE_WORKTREE:-0}" == "1" ]]; then
  REPO_ROOT=$(git -C "$WORKDIR" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -z "$REPO_ROOT" ]]; then
    echo "--worktree needs --cwd inside a git repo (got: $WORKDIR)" >&2
    exit 1
  fi
  SLUG=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
  WT_DIR="$(dirname "$REPO_ROOT")/$(basename "$REPO_ROOT")-wt/$SLUG"

  if [[ -d "$WT_DIR" ]]; then
    echo "reusing existing worktree: $WT_DIR"
  elif [[ -n "${WORKTREE_BRANCH:-}" ]]; then
    if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$WORKTREE_BRANCH"; then
      git -C "$REPO_ROOT" worktree add "$WT_DIR" "$WORKTREE_BRANCH" >&2 || exit 1
    else
      git -C "$REPO_ROOT" worktree add -b "$WORKTREE_BRANCH" "$WT_DIR" >&2 || exit 1
    fi
  else
    git -C "$REPO_ROOT" worktree add -b "$SLUG" "$WT_DIR" >&2 || exit 1
  fi

  WORKDIR="$WT_DIR"
  echo "worktree: $WORKDIR ($(git -C "$WORKDIR" branch --show-current))"
fi

CURRENT=$(cmux current-workspace 2>&1 | awk '{print $1}')
NEW_WINDOW=""
NEW_WINDOW_DEFAULT_WORKSPACE=""

if [[ "$OPEN_NEW_WINDOW" == "1" ]]; then
  NEW_WINDOW=$(cmux new-window 2>&1 | awk '{print $1}')
  NEW_WINDOW_DEFAULT_WORKSPACE=$(cmux list-workspaces --window "$NEW_WINDOW" 2>&1 | awk '/workspace:/ {print $1; exit}')
fi

if [[ -n "$PROMPT" ]]; then
  TMPFILE=$(mktemp /tmp/spawn-prompt.XXXXXX)
  printf '%s' "$PROMPT" > "$TMPFILE"
  # Pass prompt via temp file to avoid shell quoting issues (content starting
  # with `---`, backticks, unmatched quotes, etc.). The agent reads the file
  # and outputs the brief so the user can see it in the workspace scrollback.
  LAUNCH_INSTRUCTION="Read the file at $TMPFILE in full. First, output its contents so the user can see the handoff brief in this workspace. Then execute its instructions."
  # CMUX_QUIET=1 + pattern-extract: alias-deprecation notices land in 2>&1 and
  # break positional `awk '{print $2}'`, making rename target the wrong workspace.
  NEW_UUID=$(CMUX_QUIET=1 cmux new-workspace --cwd "$WORKDIR" --command "cd \"$WORKDIR\" && exec $RUNNER \"$LAUNCH_INSTRUCTION\"" 2>&1 | grep -oE 'workspace:[0-9]+' | tail -1)
else
  NEW_UUID=$(CMUX_QUIET=1 cmux new-workspace --cwd "$WORKDIR" --command "cd \"$WORKDIR\" && exec $RUNNER" 2>&1 | grep -oE 'workspace:[0-9]+' | tail -1)
fi

cmux rename-workspace --workspace "$NEW_UUID" "$NAME" 2>&1

if [[ -n "$NEW_WINDOW" ]]; then
  cmux move-workspace-to-window --workspace "$NEW_UUID" --window "$NEW_WINDOW" 2>&1 || true
  if [[ -n "$NEW_WINDOW_DEFAULT_WORKSPACE" && "$NEW_WINDOW_DEFAULT_WORKSPACE" != "$NEW_UUID" ]]; then
    cmux close-workspace --workspace "$NEW_WINDOW_DEFAULT_WORKSPACE" >/dev/null 2>&1 || true
  fi
fi

# Auto-dismiss Claude Code's "trust this folder" prompt on first launch in a new
# directory. Inline poll (background subshells get killed when the parent exits
# under the Claude Code Bash tool). Polls up to ~8s; answers when the prompt is
# detected. Since Claude Code 2.1.270 the default selection is "No, exit", so a
# bare Enter quits the agent and cmux closes the workspace within seconds.
# Send Down to reach "Yes, I trust", then Enter. On older
# builds Down lands on the second option too, which is still "Yes" in both layouts.
# Fast-exits as soon as the prompt is handled. No-op if it never appears.
for _ in $(seq 1 16); do
  SCREEN=$(cmux read-screen --workspace "$NEW_UUID" 2>&1 || true)
  if echo "$SCREEN" | grep -q "trust this folder"; then
    cmux send-key --workspace "$NEW_UUID" Down >/dev/null 2>&1 || true
    sleep 0.3
    cmux send-key --workspace "$NEW_UUID" Enter >/dev/null 2>&1 || true
    break
  fi
  sleep 0.5
done

SESSION_PATH=""
if [[ "$WRITE_SESSION" == "1" ]]; then
  # All session notes are filed flat here, date-prefixed, with `agent:` in the
  # frontmatter discriminating which harness wrote them.
  SESSIONS_DIR="$AGENT_NOTES/Sessions"
  mkdir -p "$SESSIONS_DIR"

  DATE=$(date +%Y-%m-%d)
  SLUG=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g')
  SESSION_FILE="${SESSIONS_DIR}/${DATE} ${NAME}.md"

  # Avoid clobbering existing session with the same name today
  if [[ -e "$SESSION_FILE" ]]; then
    SESSION_FILE="${SESSIONS_DIR}/${DATE} ${NAME} ${NEW_UUID:0:8}.md"
  fi

  GOAL_LINE="${GOAL:-$PROMPT}"
  # Indent each line by 2 spaces for a YAML literal block scalar.
  # Obsidian's Properties parser breaks on multi-line double-quoted scalars; literal blocks (|) are safe.
  GOAL_BLOCK=$(printf '%s\n' "$GOAL_LINE" | sed 's/^/  /')

  cat > "$SESSION_FILE" <<EOF
---
categories:
  - "[[Sessions]]"
topics: []
type: "[[Sessions]]"
agent: ${SESSION_AGENT}
model: ${ROUTE_MODEL_ID}
effort: ${EFFORT:-unset}
date: ${DATE}
status: in-progress
workspace_name: "${NAME}"
workspace_id: "${NEW_UUID}"
goal: |
${GOAL_BLOCK}
definition_of_done:
related:
  - "[[Sessions]]"
created: ${DATE}
---

## Goal

${GOAL_LINE}

## Definition of Done

- [ ]

## Progress

- ${DATE}: workspace spawned.
- route default: ${ROUTE_DEFAULT}
- route dispatched: ${ROUTE_DISPATCHED}
- route reason: ${ROUTE_REASON}

## Comments

## Outcome
EOF

  SESSION_PATH="$SESSION_FILE"
fi

cmux select-workspace --workspace "$CURRENT" 2>&1
echo "Workspace '$NAME' ready (uuid: $NEW_UUID)"
if [[ -n "$SESSION_PATH" ]]; then
  echo "Session note: $SESSION_PATH"
fi
echo "$ROUTE_LINE"
