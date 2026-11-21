# Sub-1-Minute CI Speed and Cost Workflow

Follow the playbook below verbatim during Pillar 3 of `/hygiene` (or when
running a focused `ci` pass) for any repository with automated CI workflows.

## Core Playbook (Verbatim)

Make this repo's CI as fast as possible without letting it lie. Target: a PR gets its result in under 1 minute at the median and under 2 at p95.

Three rules outrank speed:

- The full suite runs before anything reaches main, in a merge queue. Selection only narrows PR feedback.
- Never hide failures. No retries, wider timeouts or skipped tests. A check that needs a retry has a bug; find it.
- Never check less. Lint rules and required checks only stay or grow.

First, audit. Pull the last 150 runs and split every job into waiting, setup and running, at p50 and p95. Fix the biggest bucket first.

Then hit these budgets:

- Waiting, under 5 seconds: cancel a branch's in-progress run when a new commit lands, and keep runners warm where queue wait exceeds budget.
- Setup, under 15 seconds: bake the toolchain into the runner image. Get PR cache hits above 95% by seeding caches from main, and cache node_modules itself. Use a blobless clone (`filter: blob:none`).
- Slowest job, under 35 seconds. No required job waits on another.
- Lint, under 1 second: `bun lint`. It reads the existing `.oxlintrc.json`. Turn on every rule you can.
- Format, under 1 second: `bun fmt`.
- Typecheck, under 5 seconds: `bun check` on TypeScript 7.
- Tests, under 30 seconds per shard: `bun test`. Test files keep their `vitest` imports. Isolate modules, not processes, reset state after every file, and run in random order to flush out leaks.
- Install and scripts: bun. Delete npm, yarn, pnpm, Prettier, ESLint, oxlint, Vitest and Jest. If a tool only exists in a canary, pin that exact canary.
- Shards: buy cores before shards, match workers to cores, and give each shard its own throwaway database. Split any test file over 20 seconds. Balance shards from file times that main records on every full run, and prove the shards together ran every file.
- Fewer tests, on evidence: for two weeks, log every test failure you fix as a caught regression or a change detector. Delete the files that only detect change and ban their patterns in AGENTS.md. Never delete tests for authorization, privacy, migrations or concurrency.
- Shape: run lint, typecheck, build and tests in parallel. Fold the small checks into one job that lists every failure.
- Selection: on PRs, run only the tests the diff can reach, and list the inputs that rerun everything. Then hide a real change from it on purpose and confirm CI goes red.
- Local, under 9 seconds: hk hooks. Pre-commit formats and lints staged files; pre-push runs the same check as CI. A hook, not a line in AGENTS.md, because agents skip steps.
- Keep it fast: fail any job that exceeds its budget.

The tools above are defaults; you need a measured reason to keep an old one. Before each switch, run old and new side by side and list anything the new one misses.

One small PR per change, with before and after numbers from real runs. Do everything you can without me first; bring anything that needs an account, a secret or a bigger bill as one list with expected monthly cost. End with total CI time and cost, before and after.

## Audit Tooling and Stack Notes

- **Step 1 command**: Run `python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150 --json` to pull up to 150 completed runs, split every job into waiting, setup, and running at p50 and p95, and compute monthly billable runner-minutes plus uncancelled PR overlap waste.
- **Backend builds**: For server or full-stack suites, build the backend app once per process rather than rebuilding per test file.
- **Non-JS/TS stacks**: Apply the same budgets and rules with native equivalents. For Python repositories, map `bun` install to cached `uv`, `bun lint` and `bun fmt` to `ruff`, and `bun test` shards to balanced `pytest` shards with a verification check proving 100% file coverage.
- **Personal GitHub repositories**: Native GitHub Merge Queues are available only on public organisation repositories or GitHub Enterprise Cloud. On personal repositories, run the full suite on `push` to `main`, keep `merge_group` triggers wired for portability, and enforce required checks plus up-to-date branch protection before merge.
- **Audit-only gate**: When `/hygiene` runs in `Audit only` mode, complete the 150-run audit, inspect workflows, skipped tests, branch protection, and failure logs, and deliver the ranked small-PR plan plus the single monthly-cost approval list without editing files.
