# Orchestration hosts

T3 Code is the primary orchestration host. Follow T3 Code's injected tool rules
first. Optional `cmux` workspace mechanics live in `../cmux/`. All model,
provider, health and takeover decisions run through
`../model-routing/scripts/preflight.py` (or a personal CLI wrapper such as
`b route` if you maintain one in your private Home Repo).

## Dispatch in T3 Code

In T3 Code, use `delegate_task` whenever working across providers, in a
separate worktree, outside your primary checkout or when targeting a linked
environment. Force `isolation: "shared"` whenever `target.environmentId` names
a linked environment.

1. Call `orchestrator_capabilities` once per thread before the first `delegate_task`.
2. Run `python3 ../model-routing/scripts/preflight.py preflight --host t3 --category <cat> --capabilities <json> [--environment-id <id>] --json` (adding `--of <cat> --builder <provider>` for `review`).
3. Pass `targets[0].delegate_target` (`providerInstanceId`, `driverKind`, `model`, `options`) and `isolation` straight to `delegate_task`. Keep `isolation: "shared"` on linked environments and `isolation: "worktree"` on local repositories.
4. Write a short pointer-based brief using `workflows/dispatch.md` and `references/worker-behaviours.md`.
5. Record the `taskId`, thread link, selected target and checkout in the session note. If `preflight` exits `3`, report the skip reasons and pause for a ruling.

## Dispatch in cmux and CLI

For `cmux` or standalone CLI runs, call the same routing core with the matching
host adapter:

```bash
python3 ../model-routing/scripts/preflight.py preflight --host cmux --category <cat> --json
python3 ../model-routing/scripts/preflight.py preflight --host cli --category <cat> --json
```

Pass `targets[0].agent` and `targets[0].cli_flags` to `cmux`, or
`targets[0].target` (`provider`, `model`, `effort`) to a plain CLI runner.

## Automated takeover

When a worker fails at launch or mid-flight, run `takeover` with the active
host adapter (`--host t3`, `--host cmux` or `--host cli`):

```bash
python3 ../model-routing/scripts/preflight.py takeover --host t3 \
  --category <cat> --failed-provider <provider> --failed-model <model> \
  --error "<error text>" --attempt <n> [--worktree <path>] --capabilities <json> --json
```

For review tasks, pass `--category review --of <cat> --builder <provider>`.
Follow the returned `salvage` action (`task_cancel` on zero-edit launch
failures, or preserve the worktree and pass `salvage.brief_context` into the
replacement brief). Escalate to the user whenever `takeover` exits `3`.

## Long-run checkpoint contract

Keep delegated slices bounded (target under 20 minutes). For long runs,
instruct the worker to append timestamped progress checkpoints to the session
note or commit incrementally on its branch. If oversight is needed, arm at most
one optional 30-minute escalation check that inspects the session note and git
log and alerts the user when stalled. Never run `task_status` polling loops or
blind auto-kills.

## Status, relay, handoff and visuals

Use `task_cancel` for unneeded child work, `t3_thread_read` before reporting on
a top-level thread, and `t3_thread_send` to relay to a peer. T3 completion
wakeups replace terminal polling. Interactive coordinators and long-lived
top-level threads write handoff briefs to `$AGENT_NOTES/Sessions/Handoffs/` and
session notes to `$AGENT_NOTES/Sessions/` with `agent:` and `host: t3-code`,
handing off at 30% context usage or 300k tokens, whichever comes first. Bounded
`delegate_task` children and workflow workers are exempt and complete their
single ticket. Create a new top-level thread only when explicitly requested.

## Browser and visual output

Show rendered HTML visuals with `html_preview` then `html_render` without a
local server. Use `preview_*` only when browser work is requested, closing any
tab opened by the agent before replying unless the user asked to keep it open.
