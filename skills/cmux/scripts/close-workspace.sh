#!/bin/bash
# Close a cmux workspace and flip its session-note status to "done".
# Usage: close-workspace.sh <workspace-ref-or-name>
#
# Looks up the workspace's UUID, greps Sessions/ for a note whose
# frontmatter `workspace_id` matches, sets `status: done` and stamps `ended:`.
# Then runs `cmux close-workspace`.
#
# cmux reuses workspace numbers, so a `workspace_id` match alone also hits every
# note from a long-closed seat that held the same slot - on a busy machine that
# is dozens of notes per slot. Only a note that is still open is flipped; a
# closed one is reported and left alone.
#
# CMUX_SESSIONS_DIR overrides the notes directory (used by the test script).

set -e

ARG="${1:?Usage: close-workspace.sh <workspace:N | workspace-name>}"

if [[ "$ARG" == workspace:* ]]; then
  WS_ID="$ARG"
else
  WS_ID=$(cmux list-workspaces 2>&1 | awk -v n="$ARG" '$0 ~ ("[[:space:]]" n "$") {for (i=1;i<=NF;i++) if ($i ~ /^workspace:[0-9]+$/) {print $i; exit}}')
  if [[ -z "$WS_ID" ]]; then
    echo "No workspace named '$ARG'" >&2
    exit 1
  fi
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
  echo "No open session note for $WS_ID; $SKIPPED closed note(s) left untouched (closing anyway)"
fi

cmux close-workspace --workspace "$WS_ID" 2>&1
