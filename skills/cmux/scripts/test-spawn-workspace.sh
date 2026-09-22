#!/bin/bash
# Fixture test for spawn-workspace.sh. Runs the helper with --dry-run against the
# orchestrator skill's routing table, so nothing is spawned and no note written.
# Run it after any edit to spawn-workspace.sh, or to the orchestrator's table,
# metadata or resolver.
#
# Run: skills/cmux/scripts/test-spawn-workspace.sh
set -u
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")" && pwd)"
HELPER="$HERE/spawn-workspace.sh"
RESOLVER="$HERE/../../orchestrator/scripts/resolve.py"
export CMUX_AGENT_LAUNCH_KIND=claude

if [[ ! -f "$RESOLVER" ]]; then
  echo "FAIL  the orchestrator package is missing: $RESOLVER" >&2
  echo "      spawn-workspace.sh routes through the orchestrator skill; install both." >&2
  exit 1
fi
if ! python3 -c 'import yaml' 2>/dev/null; then
  echo "SKIP  PyYAML is not installed, so the resolver cannot read the table." >&2
  echo "      Install it with: pip install PyYAML" >&2
  exit 0
fi

pass=0; fail=0
check() {  # check <label> <expected-rc> <grep-pattern> -- <helper args...>
  local label="$1" want_rc="$2" pattern="$3"; shift 3; [[ "$1" == "--" ]] && shift
  local out rc
  out="$("$HELPER" "$@" 2>&1)"; rc=$?
  if [[ "$rc" -eq "$want_rc" ]] && printf '%s' "$out" | grep -q -- "$pattern"; then
    pass=$((pass+1)); echo "PASS  $label"
  else
    fail=$((fail+1)); echo "FAIL  $label (rc=$rc, wanted $want_rc, pattern: $pattern)"; printf '%s\n' "$out" | sed 's/^/      /'
  fi
}

# The shipped placeholder table: A-* are real Claude IDs, B-* are deliberately invalid.
check "bare call is refused with the tier list"      2 "Pass --tier"                                            -- t-bare --dry-run
check "tier A launches the small A model"            0 "exec claude --dangerously-skip-permissions --model 'claude-haiku-4-5-20251001' --effort 'medium'" -- t-a --tier A --dry-run
check "tier C launches the mid A model"              0 "exec claude --dangerously-skip-permissions --model 'claude-sonnet-5' --effort 'high'"  -- t-c --tier C --dry-run
check "tier E launches the large A model at xhigh"   0 "exec claude --dangerously-skip-permissions --model 'claude-opus-5' --effort 'xhigh'"   -- t-e --tier E --dry-run
check "the route line names tier, model and provider" 0 "route: tier E → A-Large · xhigh (provider_a)"          -- t-e --tier E --dry-run
check "an unconfigured meter reads as unread"        0 "capacity unread"                                        -- t-e --tier E --dry-run
check "--reason reaches the route line"              0 "prior pass found no cause"                              -- t-rs --tier E --reason "prior pass found no cause" --dry-run
check "review of tier E avoids the builder"          0 "route: tier R"                                          -- t-r --tier R --of E --builder provider_a --dry-run
check "explicit model and effort bypass the table"   0 "exec claude --dangerously-skip-permissions --model 'claude-opus-5' --effort 'medium'"  -- t-x --model claude-opus-5 --effort medium --dry-run
check "an unknown tier is refused"                   2 "unknown tier"                                           -- t-z --tier Z --dry-run
check "the effort reaches the session-note preview"  0 "dry-run: note agent=claude-code model=claude-opus-5 effort=xhigh" -- t-p --tier E --prompt "hello" --dry-run
check "--help exits before anything is spawned"      0 "Spawn a named cmux workspace"                           -- --help
check "a flag in the name position is refused"       2 "begins with a dash"                                     -- --tier E

echo
echo "passed $pass, failed $fail"
[[ "$fail" -eq 0 ]]
