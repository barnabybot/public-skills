#!/bin/bash
# Fixture test for close-workspace.sh's open-note guard.
# Run: skills/cmux/scripts/test-close-workspace.sh

set -u

SCRIPT="$(cd "$(dirname "$0")" && pwd)/close-workspace.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

NOTES="$TMP/Sessions"
BIN="$TMP/bin"
mkdir -p "$NOTES" "$BIN"

# Stub cmux so the test never touches a live workspace; record the close call.
cat > "$BIN/cmux" <<'STUB'
#!/bin/bash
echo "$@" >> "$CMUX_CALLS"
STUB
chmod +x "$BIN/cmux"

note() { # note <file> <workspace_id> <status> [ended]
  {
    echo "---"
    echo "agent: claude-code"
    echo "status: $3"
    [[ -n "${4:-}" ]] && echo "ended: $4"
    echo "workspace_id: \"$2\""
    echo "---"
    echo
    echo "## Progress"
  } > "$NOTES/$1"
}

note "open.md"     "workspace:8"  "in-progress"
note "review.md"   "workspace:8"  "review"
note "blocked.md"  "workspace:8"  "blocked"
note "closed.md"   "workspace:8"  "done"        "2026-01-01"
note "failed.md"   "workspace:8"  "failed"
note "other.md"    "workspace:13" "in-progress"

export CMUX_SESSIONS_DIR="$NOTES"
export CMUX_CALLS="$TMP/calls"
export PATH="$BIN:$PATH"

OUT=$("$SCRIPT" workspace:8 2>&1)
RC=$?
TODAY=$(date +%Y-%m-%d)
FAILURES=0

check() { # check <description> <condition-result>
  if [[ "$2" == "0" ]]; then
    echo "ok   - $1"
  else
    echo "FAIL - $1"
    FAILURES=$((FAILURES + 1))
  fi
}

flipped() { # flipped <file>
  grep -q "^status: done$" "$NOTES/$1" && grep -q "^ended: $TODAY$" "$NOTES/$1"
}

check "exits 0" "$RC"

for f in open.md review.md blocked.md; do
  flipped "$f"; check "$f flipped to done and stamped today" "$?"
done

grep -q "^status: done$" "$NOTES/closed.md" && grep -q "^ended: 2026-01-01$" "$NOTES/closed.md"
check "closed.md keeps its own ended date" "$?"

grep -q "^status: failed$" "$NOTES/failed.md" && ! grep -q "^ended:" "$NOTES/failed.md"
check "failed.md is left alone" "$?"

grep -q "^status: in-progress$" "$NOTES/other.md" && ! grep -q "^ended:" "$NOTES/other.md"
check "a note on another workspace id is untouched" "$?"

echo "$OUT" | grep -q "Skipped (already ended): closed.md"
check "the skip of an ended note is reported" "$?"

echo "$OUT" | grep -q "Skipped (status: failed): failed.md"
check "the skip of a failed note is reported" "$?"

grep -q "close-workspace --workspace workspace:8" "$CMUX_CALLS"
check "the workspace is still closed" "$?"

# Every match already closed: the helper says so and closes anyway.
rm -f "$NOTES"/open.md "$NOTES"/review.md "$NOTES"/blocked.md
: > "$CMUX_CALLS"
OUT2=$("$SCRIPT" workspace:8 2>&1)
echo "$OUT2" | grep -q "No open session note for workspace:8"
check "all-skipped run reports no open note" "$?"
grep -q "close-workspace --workspace workspace:8" "$CMUX_CALLS"
check "all-skipped run still closes the workspace" "$?"

# No note at all: the original message survives.
OUT3=$("$SCRIPT" workspace:99 2>&1)
echo "$OUT3" | grep -q "No session note found for workspace:99"
check "unmatched id reports no note found" "$?"

echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "close-workspace guard: all checks passed"
  exit 0
fi
echo "close-workspace guard: $FAILURES check(s) failed"
exit 1
