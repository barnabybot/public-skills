#!/bin/bash
# Close a cmux workspace and flip its session-note status to "done".
# Usage: close-workspace.sh <workspace-ref-or-name>
#
# Looks up the live workspace's number and name, finds matching session notes,
# sets `status: done` and stamps `ended:`.
# Then runs `cmux close-workspace`.
#
# cmux reuses workspace numbers, so a `workspace_id` match alone also hits every
# note from a long-closed seat that held the same slot (13 notes for
# workspace:8, 22 for workspace:13 on 2026-08-29). Only a note that is still
# open and has the current live name is flipped; other matches are reported
# and left alone.
#
# CMUX_SESSIONS_DIR overrides the notes directory (used by the test script).

set -e

ARG="${1:?Usage: close-workspace.sh <workspace:N | workspace-name>}"

if [[ "${2:-}" == --exit-idle-codex ]]; then
  if [[ "$#" -ne 4 || ! "$ARG" =~ ^workspace:[0-9]+$ ]]; then
    echo "Retained: use workspace:N --exit-idle-codex <UUID> <note-path>" >&2
    exit 2
  fi
  export CMUX_IDLE_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec python3 - "$ARG" "$3" "$4" <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import UUID

sys.path.insert(0, os.environ["CMUX_IDLE_LIB"])
import idle_codex

ref, expected_uuid, note_path = sys.argv[1:]

def cmux(*args, as_json=False):
    flags = ["--json", "--id-format", "both"] if as_json else []
    result = subprocess.run(["cmux", *flags, *args], capture_output=True,
                            text=True, check=True, timeout=10,
                            env=dict(os.environ, CMUX_QUIET="1"))
    return json.loads(result.stdout) if as_json else result.stdout

def live():
    rows = []
    for window in cmux("list-windows", as_json=True):
        listing = cmux("list-workspaces", "--window", window["id"], as_json=True)
        rows.extend(dict(w, window_id=window["id"]) for w in listing["workspaces"])
    by_uuid = [w for w in rows if w["id"].upper() == expected_uuid]
    by_ref = [w for w in rows if w["ref"] == ref]
    if not by_uuid and not by_ref:
        return None
    if len(by_uuid) != 1 or len(by_ref) != 1 or by_uuid[0] != by_ref[0]:
        raise ValueError("workspace UUID and ref do not identify one live seat")
    workspace = by_uuid[0]
    if workspace["title"] != note["workspace_name"]:
        raise ValueError("live workspace name differs from the exact note")
    return {k: workspace[k] for k in ("id", "ref", "title", "window_id")}

def terminal():
    layout = cmux("list-panes", "--workspace", expected_uuid, as_json=True)
    panes = [
        pane for pane in layout["panes"]
        if not (pane.get("dock_scope") == "global" and not pane.get("surface_ids"))
    ]
    if layout["workspace_id"].upper() != expected_uuid or len(panes) != 1 or len(panes[0]["surface_ids"]) != 1:
        raise ValueError("workspace must have one pane with one terminal")
    listing = cmux("list-pane-surfaces", "--workspace", expected_uuid,
                   "--pane", panes[0]["id"], as_json=True)
    surfaces = listing["surfaces"]
    if (listing["workspace_id"].upper() != expected_uuid or listing["pane_id"] != panes[0]["id"]
            or len(surfaces) != 1 or surfaces[0]["type"] != "terminal"
            or surfaces[0]["id"] != panes[0]["surface_ids"][0]):
        raise ValueError("workspace must have one verified terminal")
    return str(UUID(surfaces[0]["id"])).upper()

def idle(surface):
    try:
        screen = cmux("read-screen", "--workspace", expected_uuid,
                      "--surface", surface, "--lines", "40")
    except subprocess.CalledProcessError as error:
        if live() is None:
            print(error.stderr or error.stdout, file=sys.stderr, end="")
            return False
        raise
    verdict = idle_codex.prove_file(screen, expected_uuid, surface)
    if verdict != "idle":
        raise ValueError(f"Codex seat is {verdict}")
    return True

def retire():
    workspace = live()
    if workspace is None:
        print(f"Already absent: {expected_uuid}; no action taken")
        return
    surface = terminal()
    if not idle(surface):
        print(f"Already absent: {expected_uuid}; disappeared before screen read, no action taken")
        return
    if live() != workspace or terminal() != surface or Path(note_path).read_text() != note_text:
        raise ValueError("workspace, terminal or note changed before exit")
    if not idle(surface):
        print(f"Already absent: {expected_uuid}; disappeared before screen read, no action taken")
        return
    if live() != workspace or terminal() != surface or Path(note_path).read_text() != note_text:
        raise ValueError("workspace, terminal or note changed after the idle check")
    print(cmux("send-key", "--workspace", expected_uuid,
               "--surface", surface, "ctrl+d"), end="")
    for attempt in range(20):
        if live() is None:
            print(f"Retired: {expected_uuid} absent from all windows; note preserved")
            return
        if attempt > 0:
            try:
                print(cmux("close-workspace", "--workspace", expected_uuid), end="")
            except subprocess.CalledProcessError as error:
                if "confirmation_required" not in (error.stderr + error.stdout):
                    if live() is not None:
                        raise
                print(error.stderr or error.stdout, file=sys.stderr, end="")
        time.sleep(0.25)
    raise ValueError("normal exit is pending; workspace UUID remains live")

try:
    expected_uuid = str(UUID(expected_uuid)).upper()
    note_text = Path(note_path).read_text()
    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", note_text, re.S)
    if frontmatter is None:
        raise ValueError("exact note has no frontmatter")
    note = {}
    for line in frontmatter[1].splitlines():
        key, separator, value = line.partition(":")
        if separator and key in ("agent", "status", "ended", "workspace_id", "workspace_name"):
            if key in note:
                raise ValueError("exact note has ambiguous identity or status")
            value = value.strip()
            note[key] = json.loads(value) if value.startswith('"') else value
    if note.get("agent") != "codex" or note.get("workspace_id") != ref or not note.get("workspace_name"):
        raise ValueError("exact note does not identify this Codex seat")
    if note.get("status") not in ("done", "failed") and not note.get("ended"):
        raise ValueError("exact Codex note is still open")
    retire()
except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
    if isinstance(error, subprocess.CalledProcessError):
        print(error.stderr or error.stdout, file=sys.stderr, end="")
    print(f"Retained: {error}", file=sys.stderr)
    sys.exit(1)
PY
fi

if [[ "$#" -ne 1 ]]; then
  echo "Retained: unknown close-workspace arguments" >&2
  exit 2
fi

find_workspace() {
  awk -v arg="$ARG" '
  match($0, /workspace:[0-9]+[[:space:]]+/) {
    id = substr($0, RSTART, RLENGTH)
    name = substr($0, RSTART + RLENGTH)
    sub(/[[:space:]]+$/, "", id)
    sub(/[[:space:]]+\[selected\][[:space:]]*$/, "", name)
    sub(/[[:space:]]+$/, "", name)
    if ((arg ~ /^workspace:/ && arg == id) ||
        (arg !~ /^workspace:/ && arg == name)) {
      print id "\t" name
      exit
    }
  }
  '
}

LIVE_WORKSPACE=$(cmux list-workspaces 2>&1 | find_workspace)
if [[ -z "$LIVE_WORKSPACE" && "$ARG" == workspace:* ]]; then
  while IFS= read -r window; do
    LIVE_WORKSPACE=$(cmux list-workspaces --window "$window" 2>&1 | find_workspace)
    [[ -n "$LIVE_WORKSPACE" ]] && break
  done < <(cmux list-windows 2>/dev/null | awk '{for (i=1; i<NF; i++) if ($i ~ /^[0-9]+:$/) {print $(i+1); break}}')
fi
WS_NAME=""
if [[ "$ARG" == workspace:* ]]; then
  WS_ID="$ARG"
else
  if [[ -z "$LIVE_WORKSPACE" ]]; then
    echo "No workspace named '$ARG'" >&2
    exit 1
  fi
  WS_ID="${LIVE_WORKSPACE%%$'\t'*}"
fi
if [[ -n "$LIVE_WORKSPACE" ]]; then
  WS_NAME="${LIVE_WORKSPACE#*$'\t'}"
fi

SESSIONS_DIR="${CMUX_SESSIONS_DIR:-${AGENT_NOTES:-$HOME/agent-notes}/Sessions}"
TODAY=$(date +%Y-%m-%d)
MATCHED=0
SKIPPED=0

# `grep -l --null` gives the NUL separator this loop reads. On macOS `-Z` is
# --decompress, so the earlier `grep -lZ` returned newline-separated paths,
# `read -d ''` found no NUL, and the loop ran zero times on every close while
# the helper reported "No session note found".
if [[ -d "$SESSIONS_DIR" ]]; then
  while IFS= read -r -d '' f; do
    if grep -q '^ended:' "$f"; then
      echo "Skipped (already ended): $(basename "$f")"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    STATUS=$(grep -m1 '^status:' "$f" | sed 's/^status:[[:space:]]*//; s/[[:space:]]*$//')
    case "$STATUS" in
      in-progress|review|blocked) ;;
      *)
        echo "Skipped (status: ${STATUS:-none}): $(basename "$f")"
        SKIPPED=$((SKIPPED + 1))
        continue
        ;;
    esac
    NOTE_NAME=$(awk '
      NR == 1 { if ($0 != "---") exit; next }
      /^---$/ { exit }
      /^workspace_name: ".*"$/ {
        sub(/^workspace_name: "/, ""); sub(/"$/, ""); print; exit
      }
    ' "$f")
    if [[ -z "$WS_NAME" || "$NOTE_NAME" != "$WS_NAME" ]]; then
      echo "Skipped (workspace number only): $(basename "$f")"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    sed -i '' "s/^status: ${STATUS}$/status: done/" "$f"
    sed -i '' "/^status: done$/a\\
ended: $TODAY
" "$f"
    echo "Updated: $(basename "$f")"
    MATCHED=$((MATCHED + 1))
  done < <(grep -l --null "^workspace_id: \"$WS_ID\"" "$SESSIONS_DIR"/*.md 2>/dev/null || true)
fi

if [[ "$MATCHED" -eq 0 && "$SKIPPED" -eq 0 ]]; then
  echo "No session note found for $WS_ID (closing anyway)"
elif [[ "$MATCHED" -eq 0 ]]; then
  echo "No open session note for $WS_ID with the current name; $SKIPPED note(s) left untouched (closing anyway)"
fi

cmux close-workspace --workspace "$WS_ID" 2>&1
