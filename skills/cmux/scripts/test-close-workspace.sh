#!/bin/bash

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
if [[ "$1" == list-workspaces ]]; then
  if [[ "${3:-}" == BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB ]]; then
    printf '%s\n' '  workspace:77  Other window work'
  else
    printf '%s\n' '* workspace:8  Current [work].*  [selected]' '  workspace:13  Other work' '  workspace:99  Empty work'
  fi
elif [[ "$1" == list-windows ]]; then
  printf '%s\n' '* 0: AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA workspaces=3' '  1: BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB workspaces=1'
fi
STUB
chmod +x "$BIN/cmux"

note() {
  {
    echo "---"
    echo "agent: claude-code"
    echo "status: $3"
    [[ -n "${4:-}" ]] && echo "ended: $4"
    echo "workspace_id: \"$2\""
    echo "workspace_name: \"${5:-Current [work].*}\""
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
note "reused.md"   "workspace:8"  "in-progress" "" "Previous work"
note "body-name.md" "workspace:8" "in-progress"
sed -i '' '/^workspace_name:/d' "$NOTES/body-name.md"
printf '\n```yaml\nworkspace_name: "Current [work].*"\n```\n' >> "$NOTES/body-name.md"

export CMUX_SESSIONS_DIR="$NOTES"
export CMUX_CALLS="$TMP/calls"
export PATH="$BIN:$PATH"

OUT=$("$SCRIPT" workspace:8 2>&1)
RC=$?
TODAY=$(date +%Y-%m-%d)
FAILURES=0

check() {
  if [[ "$2" == "0" ]]; then
    echo "ok   - $1"
  else
    echo "FAIL - $1"
    FAILURES=$((FAILURES + 1))
  fi
}

flipped() {
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

grep -q "^status: in-progress$" "$NOTES/reused.md" && ! grep -q "^ended:" "$NOTES/reused.md"
check "an open note with a reused id and different name is untouched" "$?"

echo "$OUT" | grep -q "Skipped (workspace number only): reused.md"
check "a workspace number-only match is reported" "$?"

grep -q "^status: in-progress$" "$NOTES/body-name.md" && ! grep -q "^ended:" "$NOTES/body-name.md"
check "a workspace name in the body cannot match missing frontmatter" "$?"

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

OUT3=$("$SCRIPT" workspace:99 2>&1)
echo "$OUT3" | grep -q "No session note found for workspace:99"
check "unmatched id reports no note found" "$?"

note "by-name.md" "workspace:8" "in-progress"
: > "$CMUX_CALLS"
OUT4=$("$SCRIPT" 'Current [work].*' 2>&1)
check "the exact selected workspace name resolves" "$?"
flipped "by-name.md"; check "name lookup updates the matching note" "$?"
grep -q "close-workspace --workspace workspace:8" "$CMUX_CALLS"
check "name lookup closes the resolved workspace" "$?"

note "other-window.md" "workspace:77" "in-progress" "" "Other window work"
: > "$CMUX_CALLS"
OUT5=$("$SCRIPT" workspace:77 2>&1)
check "an id in another window resolves" "$?"
flipped "other-window.md"; check "another window's matching note is updated" "$?"
grep -q "close-workspace --workspace workspace:77" "$CMUX_CALLS"
check "the other window's workspace is closed" "$?"

note "missing-live.md" "workspace:404" "in-progress" "" "Missing work"
: > "$CMUX_CALLS"
OUT6=$("$SCRIPT" workspace:404 2>&1)
check "a missing live id preserves the close attempt" "$?"
grep -q "^status: in-progress$" "$NOTES/missing-live.md" && ! grep -q "^ended:" "$NOTES/missing-live.md"
check "a note without a live workspace is untouched" "$?"
grep -q "close-workspace --workspace workspace:404" "$CMUX_CALLS"
check "a missing live id still reaches the close command" "$?"

echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "close-workspace guard: all checks passed"
  exit 0
fi
echo "close-workspace guard: $FAILURES check(s) failed"
exit 1
