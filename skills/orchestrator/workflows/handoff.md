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

4. Write `$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md`. Include goal, current state, cwd/worktree, branch, relevant files, remaining work, validation, existing authorisation and unresolved decisions. Include the predecessor's model and effort for a recycle. Exclude credentials and unnecessary personal data.
5. Name the 1–3 skills the successor needs. A successor inheriting a role must load that role's skill before acting. For an orchestrator, begin: "You are the orchestrator. Load the orchestrator skill before you touch the fleet."

## Deliver

| Request | Action |
|---|---|
| Handoff or handover | Follow `workflows/handoff-auto-spawn.md`. Write the brief, spawn, verify the route, report the workspace name and ID. |
| Copy or clipboard | Follow `workflows/handoff-immediate.md`. Write the brief, copy that file, report its path. |
| Park | Follow `workflows/handoff-park.md`. Record full context in the session note. |
| Named live peer | Write the brief, send its path and the user's instruction with `cmux send`, then Enter. Verify delivery and record it in Progress. |

Carry existing authorisation forward. The successor may continue authorised work after reading the brief. State any decision that still requires the user; do not manufacture a new approval gate.

For cross-machine work, read `references/cross-machine-bridge.md`. For a recycle, also apply `workflows/recycle.md` and preserve model, effort and cwd.
