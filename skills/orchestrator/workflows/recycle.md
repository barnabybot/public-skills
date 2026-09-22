# Recycle

Read the `handoff` skill for the brief and delivery procedure.

## Recycle discipline

Context is a consumable. Plan succession before it runs out.

- **A seat with a fixed context window recycles at about 30% consumed.** The
  running agent commits its work and writes its own handoff to
  `$AGENT_NOTES/Sessions/Handoffs/` (it holds the punch-list); you spawn the successor from
  that file with the same `--agent`, `--model`, and `Effort:` as the
  predecessor, verify the new status line, and close the old workspace
  with `close-workspace.sh`.
- **A seat that auto-compacts is different.** Where the harness summarises in
  place and the seat continues, its base window is far larger and 30% is barely
  into the task. Leave it running through compaction. Recycle it on a new work
  phase, or when the job is done. A meter at 40-80% on a compacting seat is
  still working, so do not send "write your handoff" because a threshold meant
  for a different harness was crossed.
- **A new work phase always gets a fresh workspace.** Never reactivate a Claude
  worker past its threshold to open new scope, however much subject knowledge it
  holds. It will spend what remains writing a handoff, and the work starts in a
  successor anyway — one hop later. Spawn fresh from a brief that carries the
  knowledge instead. Codex seats also get a fresh workspace for a new phase;
  the compacting seat does not pick up new scope.
- **A worker held for decisions is still burning threshold.** Parking a
  past-threshold worker at `review` as a live decision surface
  fails, because the user types straight into worker composers and hands it
  fresh scope himself while you watch. That is where "it keeps making mistakes"
  landed in one run: a worker at 37% taking rollout instructions direct. Once a
  worker crosses its threshold, recycle it even with nothing in flight -
  a successor holds the decision surface just as well.
- **Your own succession is part of the job.** An orchestrator that runs itself down
  leaves the fleet without a coordinator. On a compacting seat, stay in place
  through compaction and recycle on a new phase or when the job is done. On a
  fixed-window seat, read your own meter every tick and hand off at about 30%.
- **Tell the successor to load this skill, in the first line of the handoff.** A
  succession brief carries the state of the fleet; it does not carry the rules that
  govern one, and a successor spawned from a file has no reason to reach for a skill
  nobody named. On 2026-08-13 an orchestrator ran a full seat off an inherited brief
  without ever loading this file, numbered every workspace at the user for the whole
  session, and closed two seats with `cmux close-workspace` while leaving their notes
  stuck at `in-progress`. Every rule it broke was already written here. Open the
  handoff with the instruction verbatim: **"You are the orchestrator. Load the
  `orchestrator` skill before you touch the fleet — this brief carries the state, the
  skill carries the rules."**
