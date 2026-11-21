#!/bin/bash
set -e

USAGE='Usage: spawn-workspace.sh <name> (--tier <category> | --model <id> [--effort <level>]) [--request <JSON>] [--agent codex|claude|grok] [--of <category>] [--builder <provider>] [--reason "..."] [--cwd <path>] [--worktree [branch]] [--prompt "..."] [--prompt-file <path>] [--goal "..."] [--session] [--no-session] [--same-window] [--new-window] [--loop [pct]] [--route-out <path>] [--resolved-route <path>] [--dry-run]'

SCRIPT_REAL="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
RESOLVER="${ROUTING_RESOLVER:-$(cd "$(dirname "$SCRIPT_REAL")/../../orchestrator/scripts" 2>/dev/null && pwd)/resolve.py}"
PYTHON="${SPAWN_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_REAL")" && pwd)"
STAMP_HELPER="$SCRIPT_DIR/stamp_surface.py"
HEADER_HELPER="$SCRIPT_DIR/group_header.py"

AGENT_NOTES="${AGENT_NOTES:-$HOME/agent-notes}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Spawn a named cmux workspace with Claude Code, Codex or Grok (no focus steal).' "$USAGE" \
    'See skills/orchestrator/references/routing-rules.md for routing categories and gates.'
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
REQUEST=""
ROUTE_OUT_BUNDLE=""
RESOLVED_ROUTE_BUNDLE=""
LOOP_PCT=""
DRY_RUN=0
WORKDIR="$AGENT_NOTES"

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
    --request) REQUEST="$2"; shift 2 ;;
    --route-out) ROUTE_OUT_BUNDLE="$2"; shift 2 ;;
    --resolved-route) RESOLVED_ROUTE_BUNDLE="$2"; shift 2 ;;
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
      PROMPT_FILE="$2"
      PROMPT="$(cat "$2"; printf x)"
      PROMPT="${PROMPT%x}"
      shift 2
      ;;
    --goal) GOAL="$2"; shift 2 ;;
    --session) WRITE_SESSION=1; shift ;;
    --no-session) WRITE_SESSION=0; shift ;;
    --new-window) OPEN_NEW_WINDOW=1; shift ;;
    --same-window) OPEN_NEW_WINDOW=0; shift ;;
    --loop)
      if [[ -n "${2:-}" && "$2" =~ ^[0-9]+$ ]]; then
        LOOP_PCT="$2"; shift 2
      else
        LOOP_PCT="30"; shift
      fi
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ ! -d "$WORKDIR" ]]; then
  if [[ "$WORKDIR" == "$AGENT_NOTES" ]]; then
    mkdir -p "$WORKDIR"
  else
    echo "cwd not found: $WORKDIR" >&2
    exit 1
  fi
fi

if [[ -z "$MODEL" && -z "$TIER" ]]; then
  echo "Pass --tier <category>, or --model <id> with --effort <level>. Categories:" >&2
  "$PYTHON" "$RESOLVER" --list-tiers >&2 || true
  echo "$USAGE" >&2
  exit 2
fi
if [[ ! -f "$RESOLVER" ]]; then
  echo "routing resolver not found: $RESOLVER" >&2
  exit 1
fi
if [[ -n "$REQUEST" && ! -f "$REQUEST" ]]; then
  echo "routing request not found: $REQUEST" >&2
  exit 2
fi
if [[ -n "$ROUTE_OUT_BUNDLE" && -n "$RESOLVED_ROUTE_BUNDLE" ]]; then
  echo "Pass either --route-out or --resolved-route, not both." >&2
  exit 2
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
ROUTE_ARGS+=(--runtime-cwd "$WORKDIR")
[[ -n "$REQUEST" ]] && ROUTE_ARGS+=(--request "$REQUEST")
[[ -n "$ROUTE_OUT_BUNDLE" ]] && ROUTE_ARGS+=(--bundle-out "$ROUTE_OUT_BUNDLE")
[[ -n "$RESOLVED_ROUTE_BUNDLE" ]] && ROUTE_ARGS+=(--verify-bundle "$RESOLVED_ROUTE_BUNDLE")
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
[[ -n "${ROUTE_LEGACY_NOTE:-}" ]] && echo "deprecated: $ROUTE_LEGACY_NOTE" >&2

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
PRE_EXEC_CMD=""
if [[ -f "$STAMP_HELPER" ]]; then
  PRE_EXEC_CMD="\"$PYTHON\" \"$STAMP_HELPER\" \"$SESSION_AGENT\" \"${ROUTE_MODEL_ID:-$MODEL}\" \"${EFFORT:-unset}\" \"$WORKDIR\" \"$AGENT\" && "
fi

if [[ -n "$PROMPT" && -n "$EFFORT" ]] && ! printf '%s' "$PROMPT" | head -1 | grep -q '^Effort:'; then
  PROMPT="Effort: $EFFORT"$'\n\n'"$PROMPT"
fi

SPAWN_TITLE=$(printf '%s\n' "${GOAL:-$NAME}" | head -n1 | sed 's/\\/\\\\/g; s/"/\\"/g')

if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry-run: workspace '$NAME' in $WORKDIR${USE_WORKTREE:+ (--worktree would add its own tree)}"
  echo "dry-run: exec $RUNNER"
  echo "dry-run: note agent=$SESSION_AGENT model=$ROUTE_MODEL_ID effort=${EFFORT:-unset}"
  echo "dry-run: note spawn_title=\"$SPAWN_TITLE\""
  echo "$ROUTE_LINE"
  exit 0
fi

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

SPAWN_ARGS=()
CURRENT=""
NEW_WINDOW=""
NEW_WINDOW_DEFAULT_WORKSPACE=""
CMUX_HELP=$(cmux new-workspace --help 2>&1)
if [[ "$CMUX_HELP" == *"--group-reference"* ]]; then
  SPAWN_ARGS+=(--focus false)
  if [[ "$OPEN_NEW_WINDOW" != "1" ]]; then
    IDENTITY=$(cmux identify --json --id-format uuids)
    CALLER=$(printf '%s' "$IDENTITY" | "$PYTHON" -c '
import json, os, sys
try:
    caller = json.load(sys.stdin).get("caller")
    expected = os.environ.get("CMUX_WORKSPACE_ID")
    if caller is None and not expected:
        sys.exit(0)
    workspace, window = caller["workspace_id"], caller["window_id"]
    if not workspace or not window or (expected and workspace.lower() != expected.lower()):
        raise ValueError("caller identity does not match CMUX_WORKSPACE_ID")
    print(workspace, window)
except (ValueError, KeyError, TypeError) as exc:
    sys.exit(f"Cannot resolve cmux caller: {exc}")
')
    if [[ -n "$CALLER" ]]; then
      read -r CALLER_WORKSPACE CALLER_WINDOW <<< "$CALLER"
      GROUPS_JSON=$(cmux --json --id-format uuids workspace-group list --window "$CALLER_WINDOW")
      CALLER_GROUP=$(printf '%s' "$GROUPS_JSON" | "$PYTHON" -c '
import json, sys
try:
    data = json.load(sys.stdin)
    if data["window_id"].lower() != sys.argv[2].lower() or not isinstance(data["groups"], list):
        raise ValueError("unexpected group window or groups")
    matches = []
    for group in data["groups"]:
        members = group["member_workspace_ids"]
        if not isinstance(members, list) or not isinstance(group["id"], str) or not group["id"]:
            raise ValueError("invalid group membership")
        if sys.argv[1].lower() in [member.lower() for member in members]:
            matches.append(group["id"])
    if len(matches) > 1:
        raise ValueError("caller belongs to multiple groups")
    print(matches[0] if matches else "")
except (ValueError, KeyError, TypeError, AttributeError) as exc:
    sys.exit(f"Cannot resolve cmux group: {exc}")
' "$CALLER_WORKSPACE" "$CALLER_WINDOW")
      SPAWN_ARGS+=(--window "$CALLER_WINDOW")
      if [[ -n "$CALLER_GROUP" ]]; then
        HEADER_VERDICT=$("$PYTHON" "$HEADER_HELPER" ensure --workspace "$CALLER_WORKSPACE" --window "$CALLER_WINDOW" --json)
        printf '%s' "$HEADER_VERDICT" | "$PYTHON" -c 'import json,sys; v=json.load(sys.stdin); sys.exit(0 if (v.get("group") or "").lower() == sys.argv[1].lower() else "Caller group changed before spawn")' "$CALLER_GROUP"
        SPAWN_ARGS+=(--group "$CALLER_GROUP" --group-placement afterCurrent --group-reference "$CALLER_WORKSPACE")
      fi
    fi
  fi
else
  echo "warning: this cmux lacks workspace group placement; spawning without group inheritance" >&2
  CURRENT=$(cmux current-workspace 2>&1 | awk '{print $1}')
fi

if [[ "$OPEN_NEW_WINDOW" == "1" ]]; then
  NEW_WINDOW_OUTPUT=$(cmux new-window 2>&1) || { echo "$NEW_WINDOW_OUTPUT" >&2; exit 1; }
  NEW_WINDOW=$(printf '%s\n' "$NEW_WINDOW_OUTPUT" | grep -oE 'window:[0-9]+|[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}' | tail -1)
  if [[ -z "$NEW_WINDOW" ]]; then
    echo "cmux did not return a new window reference" >&2
    exit 1
  fi
  NEW_WINDOW_DEFAULT_WORKSPACE=$(cmux list-workspaces --window "$NEW_WINDOW" 2>&1 | awk '/workspace:/ {print $1; exit}')
  if [[ -z "$CURRENT" ]]; then
    SPAWN_ARGS+=(--window "$NEW_WINDOW")
  fi
fi

if [[ -n "$PROMPT" ]]; then
  TMPFILE=$(mktemp /tmp/spawn-prompt.XXXXXX)
  printf '%s' "$PROMPT" > "$TMPFILE"
  LAUNCH_INSTRUCTION="Read the file at $TMPFILE in full. State a brief 2-3 sentence summary of the goal and next action (do not echo the full file), then execute its instructions."
  NEW_OUTPUT=$(CMUX_QUIET=1 cmux new-workspace "${SPAWN_ARGS[@]}" --cwd "$WORKDIR" --command "cd \"$WORKDIR\" && ${PRE_EXEC_CMD}exec $RUNNER \"$LAUNCH_INSTRUCTION\"" 2>&1) || { echo "$NEW_OUTPUT" >&2; exit 1; }
else
  NEW_OUTPUT=$(CMUX_QUIET=1 cmux new-workspace "${SPAWN_ARGS[@]}" --cwd "$WORKDIR" --command "cd \"$WORKDIR\" && ${PRE_EXEC_CMD}exec $RUNNER" 2>&1) || { echo "$NEW_OUTPUT" >&2; exit 1; }
fi

NEW_UUID=$(printf '%s\n' "$NEW_OUTPUT" | grep -oE 'workspace:[0-9]+' | tail -1)
if [[ -z "$NEW_UUID" ]]; then
  echo "cmux did not create the workspace; check its caller window and group" >&2
  exit 1
fi

SESSION_PATH=""
if [[ "$WRITE_SESSION" == "1" ]]; then
  SESSIONS_DIR="$AGENT_NOTES/Sessions"
  mkdir -p "$SESSIONS_DIR"

  DATE=$(date +%Y-%m-%d)
  SLUG=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g')
  SESSION_FILE="${SESSIONS_DIR}/${DATE} ${NAME}.md"

  if [[ -e "$SESSION_FILE" ]]; then
    SESSION_FILE="${SESSIONS_DIR}/${DATE} ${NAME} ${NEW_UUID:0:8}.md"
  fi

  if [[ -n "$GOAL" ]]; then
    GOAL_LINE="$GOAL"
  elif [[ -n "$PROMPT" ]]; then
    GOAL_LINE=$(printf '%s\n' "$PROMPT" | awk '
      /^Effort:[[:space:]]/ { next }
      /^[[:space:]]*---[[:space:]]*$/ { next }
      /^[[:space:]]*$/ { next }
      { sub(/^[[:space:]]*\043+[[:space:]]*/, ""); print; exit }
    ')
    [[ -z "$GOAL_LINE" ]] && GOAL_LINE="$NAME"
  else
    GOAL_LINE="$NAME"
  fi
  GOAL_BODY="$GOAL_LINE"
  if [[ -n "$PROMPT_FILE" ]]; then
    GOAL_BODY="${GOAL_LINE}"$'\n\n'"Brief: \`${PROMPT_FILE}\`"
  elif [[ -n "$PROMPT" && "${#PROMPT}" -le 400 ]]; then
    GOAL_BODY="$PROMPT"
  fi
  GOAL_BLOCK=$(printf '%s\n' "$GOAL_LINE" | sed 's/^/  /')
  SPAWN_LINES="spawn_title: \"${SPAWN_TITLE}\""
  if [[ -n "${PROMPT_FILE:-}" ]]; then
    SPAWN_LINES="handoff_brief: \"${PROMPT_FILE}\""$'\n'"${SPAWN_LINES}"
  fi
  if [[ -n "${TMPFILE:-}" ]]; then
    SPAWN_LINES="spawn_prompt: \"${TMPFILE}\""$'\n'"${SPAWN_LINES}"
  fi

  cat > "$SESSION_FILE" <<EOF
---
categories:
  - "[[Sessions]]"
topics: []
type: "[[Sessions]]"
agent: ${SESSION_AGENT}
host: cmux
model: ${ROUTE_MODEL_ID}
effort: ${EFFORT:-unset}
date: ${DATE}
status: in-progress
workspace_name: "${NAME}"
workspace_id: "${NEW_UUID}"
${SPAWN_LINES}
goal: |
${GOAL_BLOCK}
definition_of_done:
related:
  - "[[Sessions]]"
created: ${DATE}
---

## Goal

${GOAL_BODY}

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

cmux rename-workspace --workspace "$NEW_UUID" "$NAME" 2>&1

if [[ -n "$NEW_WINDOW" ]]; then
  if [[ -n "$CURRENT" ]]; then
    cmux move-workspace-to-window --workspace "$NEW_UUID" --window "$NEW_WINDOW" 2>&1 || true
  fi
  if [[ -n "$NEW_WINDOW_DEFAULT_WORKSPACE" && "$NEW_WINDOW_DEFAULT_WORKSPACE" != "$NEW_UUID" ]]; then
    if DEFAULT_VERDICT=$("$PYTHON" "$HEADER_HELPER" before-close --workspace "$NEW_WINDOW_DEFAULT_WORKSPACE" --window "$NEW_WINDOW" --json); then
      DEFAULT_UUID=$(printf '%s' "$DEFAULT_VERDICT" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["workspace"])')
      if "$PYTHON" "$HEADER_HELPER" before-close --workspace "$DEFAULT_UUID" --window "$NEW_WINDOW" --json >/dev/null; then
        cmux close-workspace --workspace "$DEFAULT_UUID" >/dev/null 2>&1 || true
      fi
    else
      echo "Retained default workspace: $DEFAULT_VERDICT" >&2
    fi
  fi
fi

if [[ -n "$LOOP_PCT" ]]; then
  LOOPS_DIR="$HOME/.claude/loops"
  mkdir -p "$LOOPS_DIR"
  echo "{\"threshold\": $LOOP_PCT}" > "$LOOPS_DIR/ws-${NEW_UUID}.json"
  echo "Loop registered at ${LOOP_PCT}% for workspace $NAME"
fi

if [[ -n "$CURRENT" ]]; then
  cmux select-workspace --workspace "$CURRENT" 2>&1
fi
echo "Workspace '$NAME' ready (uuid: $NEW_UUID)"
if [[ -n "$SESSION_PATH" ]]; then
  echo "Session note: $SESSION_PATH"
fi
echo "$ROUTE_LINE"
