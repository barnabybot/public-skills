# Handoff

Transfer the current session through a durable brief. A handoff or handover opens a new cmux workspace. Use clipboard only when the user says copy or clipboard; use park only when explicitly requested. Delivery to a named running workspace uses the live-peer procedure below.

## Prepare

1. Read this session's note, current branch and working changes. Use the named note if the user specified one. Keep the user's stated next action first.
2. Check the active work's files for `USER-COMMENT`, `NEEDS USER INPUT`, `TODO`, `FIXME` and `NEEDS CLARIFICATION`. Carry unresolved items into the brief with location and owner.
3. Update the session's Progress with these five fields. Link existing plans, commits and evidence; separate verified facts from assumptions using `references/verify-inherited-premises.md`.

   ```markdown
   ### YYYY-MM-DD (handoff)
   **Done:** Completed work and validation evidence.
   **Learned:** Findings, decisions and constraints; label assumptions.
   **Stopped at:** The exact stopping point and any unresolved decision.
   **Next:** The user's priority first, then remaining actions and owners.
   **Files:** Relevant paths, branch, worktree and links to existing evidence.
   ```

4. Write `$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md`. Include goal, current state, cwd/worktree, branch, relevant files, remaining work, validation, existing authorisation and unresolved decisions. Include the predecessor's model and effort for a recycle. Include a decision ledger: each row is tagged `direct`, `relay`, or `build`. A live-page replace or removal is `direct`. Exclude credentials and unnecessary personal data.
   For an orchestrator, include the latest author decision and its scope, verified owners, the next authorised action, work in flight, and every remaining blocker with its release condition and evidence checked. If no action is ready, record the complete assessment from [Continue authorised work](status.md#continue-authorised-work). Keep the brief self-contained for orchestration state: do not instruct the successor to read historical disposition tables, completed review receipts or active worker slice briefs in full on startup unless a status tick changes their state.
   For each push approval, record the authorised scope, attempts used and whether another attempt is authorised. Carry spent approvals forward. Preserve the recorded scope for PR creation and merge.
5. Name the 1–3 skills the successor needs. A successor inheriting a role must load that role's skill before acting. For an orchestrator, begin: "You are the orchestrator. Load the orchestrator skill before you touch the fleet."
   Include the succession record and startup instruction below for every orchestrator successor.

## Orchestrator succession

### Record the predecessor chain

Before spawning your successor, identify your caller with `cmux identify --json --id-format both`. Confirm its live workspace name and window. Use the caller identity even when another workspace has focus.

Include this section in the brief. Append yourself to the inherited predecessor list. Carry unresolved older entries forward with their session-note and handoff links. Recover missing older entries from linked handoffs for the same goal.

```markdown
### Orchestrator succession
After reading this brief and loading the orchestrator skill, complete
workflows/handoff.md#orchestrator-succession before fleet work.

| Workspace name | Workspace UUID | Window UUID | Last workspace ref | Session note | Handoff | Closure |
|---|---|---|---|---|---|---|
| <predecessor> | <stable UUID> | <window UUID> | workspace:N | <exact path> | <exact path> | pending |
```

### Start the successor

1. Read the skill, the complete brief, the frontmatter (`head -n 35`) of your own session note, and the frontmatter plus `## Progress` / `## Outcome` tail (`tail -n 60`) of the immediate predecessor's session note (do not `cat` entire multi-kilobyte historical notes). Confirm your own caller identity, route and cwd against your new session note. Record takeover readiness there before any closure.
2. Check the whole recorded predecessor chain, including older generations. If an older brief has no succession table, recover candidates from its linked session notes and handoffs. Keep active workers, unrelated orchestrators and your current workspace open.
3. Run `python3 scripts/retire_predecessors.py retire CASE.json` (`--dry-run` prints planned closes; `--json` prints the record). If a finished Codex predecessor returns `confirmation_required`, retire it with `../cmux/scripts/close-workspace.sh workspace:N --exit-idle-codex <workspace-UUID> <exact-note-path>`.

Keep session records and handoff files. Record closure as session retirement. The underlying goal continues in the successor's note.

## Deliver

| Request | Action |
|---|---|
| Handoff or handover | Follow `workflows/handoff-auto-spawn.md`. Write the brief, spawn, verify the route, report the workspace name and ID. |
| Copy or clipboard | Follow `workflows/handoff-immediate.md`. Write the brief, copy that file, report its path. |
| Park | Follow `workflows/handoff-park.md`. Record full context in the session note. |
| Named live peer | Write the brief. For Codex, send its path and the user's instruction with `../cmux/scripts/relay-codex.py` using the verified workspace and terminal UUIDs. Follow the cmux skill's relay recipe for other runtimes. Record queue acceptance and confirmed receipt separately. |

Carry existing authorisation forward. The successor may continue authorised work after reading the brief. State any decision that still requires the user; do not manufacture a new approval gate.

An orchestrator successor resumes [the continuation loop](status.md#continue-authorised-work) after the succession checks above. Reconcile inherited owners and gates before acting. Continue through authorised ready work after each result. End with the verified outcome or the complete blocker assessment.

For cross-machine work, read `references/cross-machine-bridge.md`. For a recycle, also apply `workflows/recycle.md` and preserve model, effort and cwd.
