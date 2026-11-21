# CI Speed and Cost Audit

Use this checklist during Pillar 3 of `/brun-hygiene` for any repository with
automated CI workflows. Speed never outranks honesty: full suites run before
changes reach `main`, failures are never hidden with retries or skipped tests,
and required checks only stay or grow.

## Step 1: 150-Run Audit

Run `scripts/ci_audit.py --repo <owner>/<repo> --limit 150` to pull up to the
last 150 completed runs and split every job into **waiting**, **setup**, and
**running** at p50 and p95, plus billable runner-minutes per month and
uncancelled PR overlap count. Fix the largest bucket first.

## Step 2: Target Budgets

| Bucket | Target Budget | Primary Levers |
| --- | --- | --- |
| PR wall-clock | `<60s` p50, `<120s` p95 | Path selection on PRs, parallel jobs, sharded slow suites |
| Waiting | `<5s` | Cancel superseded PR runs; consider faster runners only if wait exceeds budget |
| Setup | `<15s` | Blobless clone (`filter: blob:none`), cached package installs (`uv` / lockfile cache), preinstalled runtimes |
| Slowest job | `<35s` | Parallel workers, fixture templates, balanced verified shards (`--verify` proves 100% file coverage) |
| Small validators | Folded into 1 job | Combine `<2s` jobs into one parallel runner that lists every failure without short-circuiting |
| Local hooks | `<9s` | Staged lint/ratchets on `pre-commit`; targeted CI parity on `pre-push` |

## Step 3: Verification Discipline

- **Tool switches**: benchmark old vs new side by side and list anything the new tool misses before switching.
- **PR path selection**: list shared inputs that trigger a full rerun, fail closed on unmapped paths, and run a deliberate sabotage test confirming CI goes red on a hidden break.
- **Two-week failure log**: classify every fixed test failure as a caught regression or a change detector; remove proven change-detector tests only on evidence and never remove authorisation, privacy, migration, or concurrency tests.
- **Keep it fast**: enforce hard wall-clock budgets on fast jobs and report run-level timing summaries on every workflow run.
