# Status and coordination

T3 Code is the primary host. Use [native status, relay and handoff](../references/hosts.md#status-relay-handoff-and-visuals).
T3 completion wakeups replace terminal polling and status ticks.

## Boot

1. For interactive coordinators and long-lived top-level threads, check context usage against the 30% or 300k-token handoff ceiling and hand off first when past the limit. Bounded `delegate_task` children and workflow workers are exempt and complete their single ticket.
2. Read open session notes under `$AGENT_NOTES/Sessions/` whose frontmatter `status` is neither `done` nor `closed`.
3. For any referenced top-level T3 thread, call `t3_thread_read` before reporting its state.
4. Report a compact status table (task or thread link, route, checkout, latest progress, blockers) before dispatching new work.

## Planner and script boundary

The orchestrator plans, delegates via file pointers, verifies receipts and
relays decisions. Deterministic routing, preflight, health and takeover
decisions run through `../model-routing/scripts/preflight.py`. Workers own
investigation, builds, refactors and debugging loops.

Keep the orchestrator context light:

- Do not load heavy downstream skills or full-page screenshots into the orchestrator seat.
- Read compact worker receipts or dispatch a `review` worker via `../model-routing/scripts/preflight.py preflight --category review --of <cat> --builder <provider>` when independent verification is required.
- Execute a single verified transaction (such as one merge or one small config edit) only when no loop or debugging pass is needed.

## Serialised PR, CI, review and merge gates

Advance each deliverable through four serialised gates without skipping:

1. **Build and local verify.** Worker finishes in an isolated checkout and reports exact command outputs.
2. **PR and CI.** Push the branch, open the PR and wait for required CI checks to report green.
3. **Independent review.** Dispatch a fresh cross-provider `review` worker from a neutral brief; resolve every material finding and re-verify.
4. **Merge.** Merge only after CI is green, review findings are closed and merge approval is granted.

## Continue authorised work

After an author decision, a worker completion or your own verified action:

1. Reconcile unfinished work against current evidence, approval gates, available tools and capacity.
2. Start the next authorised ready action or relay to its owner. Verify claimed coverage before treating dependencies as satisfied.
3. Treat missing free primary-source evidence as actionable collection work before declaring a blocker.
4. End the turn only when all authorised work is done or every remaining item names its owner, blocker, release condition and evidence checked.

Preserve held publication, external-write and push approvals. Carry pending items and spent approvals into handoff briefs.

## Accepting a zero or done report

Every zero count or completion claim requires a coverage statement naming what
the check inspected and what it excluded. Report coverage alongside the
headline result. For visual or slide deliverables, require captured desktop and
mobile viewports plus the QA gate status before marking done.

## Session tracking

Keep session note frontmatter under `$AGENT_NOTES/Sessions/` valid with
`status` set to `queued`, `in-progress`, `review`, `blocked`, `done` or
`failed`, and fill in `## Outcome` plus `ended:` when closing a session.
