# Orchestration hosts

Pick the host before you run a workflow. T3 Code injects its own tool rules. Follow them. This file maps only the orchestrator seams that T3 Code does not own. A model name does not tell you the host. Route T3 work through native T3 tools rather than cmux shell helpers.

## Dispatch in T3 Code

1. Run `scripts/resolve.py` or apply the exact category, task-fit evidence, required-tool and capacity gates in `SKILL.md` and `references/routing-rules.md`. Keep the authority you already hold. Review excludes the builder provider. Hold when required capacity or access checks fail; if the host exposes no meter for your own seat, record that seat's capacity as unread in the session note.
2. Call `orchestrator_capabilities` once before the first `delegate_task`. Match the routed model and provider instance to the returned list. Put effort in `target.options` with the returned option name. Pass `isolation: "worktree"` for repository or PR work so T3 Code prepares an isolated checkout instead of sharing the main checkout or creating a worktree in the shell. If the routed model is not listed, stop and report it.
3. Write a self-contained brief in `task`. Start with `Effort: <level>`, then the Objective, Read first, Constraints, Validate, Stop when and Pause if fields, the two verbatim guard sentences, and the Progress / `status: review` rules from `workflows/dispatch.md`, plus the lines in `references/worker-behaviours.md`.
4. Record the `taskId`, the thread link, the actual model and options, and the checkout in the session note. Check required tools when the child reports.

## Status, relay and retirement in T3 Code

Use `task_cancel` for owned work you no longer need, and record each retirement candidate as retired, retained or pending with its reason in the session note. Use `t3_thread_read` before you report on a top-level thread. Use `t3_thread_send` to relay to a top-level peer. Startup retirement, `group_header.py`, screen peeks, stall traces and `close-workspace.sh` apply only in cmux. Update the session note yourself.

## Handoff and recycle in T3 Code

Write briefs to `$AGENT_NOTES/Sessions/Handoffs/` and notes to `$AGENT_NOTES/Sessions/`. Keep `agent:` as your runtime name (`codex`, `claude-code`, `antigravity`, and so on). Add `host: t3-code`. Record task IDs and thread links apart from cmux workspace IDs. List the model, effort, branch, checkout, authority, pending work and evidence. Honour the skill's 30% context-used or 300k-token ceiling; if the host exposes neither metric, recycle between phases before context degrades and state that the percentage was not available. Create a top-level thread only when the user asks for a new thread. A handoff without that request saves the brief and reports the pending continuation.

## Browser and visual output

Show rendered HTML visuals to the user with `html_preview` then `html_render`; do not start a local server for them. Use `preview_*` only when the request asks for browser work or names a page or tab, never unasked to verify your own edit. When a workflow requires rendered visual checks without requested browser work, capture headless screenshots rather than opening unasked `preview_*` tabs. In cmux keep the cmux browser defaults.

## CLI subagents

Use the current host's native subagent tool when it supports the required
provider, model and settings. Otherwise report the missing capability and save
the brief. Preserve routing, effort, approval and evidence gates. Record
`host: cli` for a plain terminal and `host: cmux` inside cmux.
