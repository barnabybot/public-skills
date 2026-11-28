# Handoff

Applies strictly to interactive coordinators and long-lived top-level threads.
Bounded `delegate_task` children and workflow workers are exempt and complete
their single ticket. Transfer the coordinator or top-level session through a
durable brief before hitting 30% context usage or 300k tokens, whichever comes
first. Follow [native handoff in T3 Code](../references/hosts.md#status-relay-handoff-and-visuals).
Create a new top-level thread only when the user explicitly asks for one.

## Prepare

1. Read this session's note, current branch and working changes. Keep the user's stated next action first.
2. Check active files for `USER-COMMENT`, `NEEDS USER INPUT`, `TODO`, `FIXME` and `NEEDS CLARIFICATION`. Carry unresolved items into the brief with location and owner.
3. Update the session note's `## Progress` with five fields, separating verified facts from assumptions via `references/verify-inherited-premises.md`:

   ```markdown
   ### YYYY-MM-DD (handoff)
   **Done:** Completed work and validation evidence.
   **Learned:** Findings, decisions and constraints; label assumptions.
   **Stopped at:** The exact stopping point and any unresolved decision.
   **Next:** The user's priority first, then remaining actions and owners.
   **Files:** Relevant paths, branch, worktree and links to existing evidence.
   ```

4. Write `$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md` with goal, current state, cwd or worktree, branch, thread links, child task IDs, relevant files, remaining work, validation, existing authorisation and unresolved decisions. Exclude credentials and personal data.
5. Name the 1 to 3 skills the successor needs. Keep the brief self-contained so the successor does not reload stale historical logs.
6. Carry existing authorisation forward without manufacturing new approval gates, while keeping held external-write, publication and push gates explicit.

## Deliver

- **Default T3 handoff**: save the brief under `$AGENT_NOTES/Sessions/Handoffs/`, update the session note, and report the brief path and pending next step.
- **Copy or clipboard**: when requested, copy the brief file and report its path.
- **Park**: when requested, record full context in the session note and mark status accordingly.
- **Live peer**: send the brief path and instruction with `t3_thread_send` for a named top-level peer thread.

For cross-machine work, read `references/cross-machine-bridge.md`.
