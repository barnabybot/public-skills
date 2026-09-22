# Verify Inherited Premises

A handoff carries a model of the world: which file is the launcher, who owns a port, where a job is registered, which branch the server runs. That model is the most useful and the most dangerous part of the brief. Past sessions show the same failure again and again — the receiving agent treated an infra or topology claim as settled fact, built on it, and only discovered the claim was stale or wrong after the work was half done.

This reference gives both sides of a handoff a discipline for those claims. The authoring side labels them. The consuming side re-confirms them. Apply it to clipboard, park, and auto-spawn handoffs alike.

## When authoring a handoff

Tag every infra, topology, or file-location claim in the brief as one of two states:

- **VERIFIED** — you ran a check this session that proved it. Quote the command or observation that proved it, inline, so the receiver can re-run it. Example: `nginx owns public 80/443 (VERIFIED: ss -ltnp shows nginx on 0.0.0.0:80 and on the public address)`.
- **ASSUMED** — you believe it but did not check it this session, or you inherited it from an earlier note. Say so plainly. Example: `the launcher is electron/main.cjs (ASSUMED, from the prior handoff)`.

A claim with no tag reads as fact. Untagged topology is how a wrong premise propagates from one session to the next, so tag it or drop it.

What counts as a load-bearing claim worth tagging:

- which process owns a host, port, or socket;
- which file is the entry point, launcher, or config that actually loads;
- where a scheduled job, route, or hook is registered;
- which branch, tag, or commit a deployment runs, and how far it has drifted from upstream;
- which service fronts a public domain.

## When consuming a handoff

Treat the inherited model as a hypothesis until you confirm it. Before you build on any load-bearing topology claim, run a live check:

1. Read the VERIFIED/ASSUMED tags first. An ASSUMED claim needs confirmation before you act on it. A VERIFIED claim still deserves a re-run if time has passed or the environment may have changed since.
2. For each claim your first actions depend on, run the cheapest check that proves or refutes it — `ss -ltnp` for who owns a port, reading the file the brief names as the launcher to confirm it actually launches, `crontab -l` and the scheduler's own job store for where a job is registered, `git status` and `git log` for branch and drift.
3. If the check refutes the claim, correct the inherited model in your session note and proceed on the confirmed topology. Record the correction so the next handoff inherits the truth.

The cost of a one-line check is small. The cost of building on a wrong premise is the whole task.

## When the objective itself rests on a premise

Tagging a claim `ASSUMED` in the brief's prose does nothing if the Goal and the
Definition of Done are written as though it were verified. An instruction phrased as
fact defeats a hedge placed anywhere else in the document.

If the job only makes sense when premise P holds, write the DoD conditionally and name
the falsification branch:

> 1. Verify P at `file:line` before changing anything.
> 2. If P holds — do X. The DoD is X.
> 3. If P fails — stop. Do not improvise a substitute job. Report the finding and
>    propose the replacement work.

**Worked example.** A brief asked a worker to "make theme scores computed again and
remove the freeze", attributing the freeze claim to a closed session's Outcome and
tagging a second claim `[BELIEF]`. Inspection found scores were already computed and
the "freeze" was the ratified baseline that a merged PR existed to honour, so the DoD
as written would have restored the defect that PR fixed. The worker stopped at the
thin-slice gate and was right to. But the brief gave it no branch, so it had to invent
the refusal and argue for it. A conditional DoD makes that outcome a success path.

## Why this lives in the handoff skill

A project's own instruction file usually warns that reference anchors - the palette source, the template source, the launcher - are the forks most often missed, and that deployment context is easy to get wrong. It rarely goes on to tell an agent to re-verify what a brief asserts. The handoff skill produces and consumes these briefs, so the instruction to label premises on the way out and re-confirm them on the way in belongs here.

## Worked example

A handoff asserted: "the desktop app launches from `electron/bootstrap-platform.cjs`." The receiving session read the file before wiring anything to it, and found it held only platform-detection helpers and a dependency-check string. The real launch lived in `electron/main.cjs`. The check was a single file read, and skipping it would have wired the new work to a file that never runs.

Had the authoring side tagged the claim `ASSUMED`, the receiver would have known to confirm it first. Had the receiver skipped the read, the error would have surfaced only after the integration failed.
