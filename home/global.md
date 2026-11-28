# Global steering

Read `<your-home-repo>/AGENTS.md` before cross-repo work or when locating a
project or vault. That file maps the Home Repo. This file supplies global rules.

## Skills and approval

Read a matching skill's `SKILL.md` before acting. Present its intake questions
first using the host's native question menu (`AskUserQuestion` or
`request_user_input`) whenever exposed and permitted. Fall back to numbered text
only when the user asks for text, the native tool is absent or prohibited, the
schema cannot represent a question, or a call fails or expires, and state the
reason before the fallback. Treat answers already supplied in the request as
settled.

Apply the Thin-Slice Gate before pushing to a public repository, publishing,
sending external messages or batch-generating several artefacts. Produce one
representative slice, show it and wait for the user's explicit go. A website
repository may publish on push. Obtain approval before that push.

## Voice and code

Use British English (`en-GB`). Write short declarative sentences. Cut filler.
Use commas, full stops or brackets instead of long dashes. Use a colon only
immediately before a list. State the affirmative claim. Remove negation-based
contrasts, invented opposing claims and repetitive parallel phrasing.

Reject stock AI vocabulary. Avoid verbs that inflate simple actions, metaphors
for routine work and claims of quality without evidence. Apply `editorial-review`
when installed. Check its banned-word list and structural voice rules.

Let code carry its meaning. Keep comments only for licences, shebangs, lint or
type directives, machine sentinels and external constraints the code cannot
express. Delete tautology and stale comments. Delete excuse comments and open
an issue for the underlying defect. Move architectural or contract decision
records to `docs/adr/NNNN-<slug>.md` before deleting the inline comment. Check
added comments with `scripts/check_code_comments.py --ratchet`. Make the
smallest change that meets the request.

## Execution, CI and test discipline

- State assumptions and surface trade-offs before coding when a choice materially
  changes the result.
- Prefer the simplest design. Add abstractions only when the task needs them.
- Make surgical edits restricted to the request.
- Define a concrete verification check for each step before acting.
- Keep pull-request CI feedback under 1 minute at p50 and under 2 minutes at
  p95. Never add retries, wider timeouts or skipped tests to paper over a red
  check. Fix the defect.
- Keep local `.githooks/pre-commit` and `.githooks/pre-push` checks fast (under
  9 seconds).
- Log red CI runs in `docs/ci-failure-log.md` for two weeks before changing any
  test. Protect tests covering security, privacy, personal-data scanning,
  ratchets and publish gates. Avoid brittle change-detector tests (full-file
  raw HTML line-count goldens, unreviewed signoff gates without a deterministic
  invariant, or exact-prose assertions on non-contract copy).

## Browser and desktop automation

Prefer CLIs and connectors where supported. When GUI or browser automation is
required, never quit or restart an app or browser the user is actively using.
Run automated browser sessions in the background where the host supports it,
close every tab you open unless asked to keep it open, and pause at login, 2FA,
passkey or payment gates with a clear note naming the waiting tab.

## Multi-agent delegation

In T3 Code, use `delegate_task` whenever working outside your primary
repository, across providers, in a separate worktree or on a linked
environment. Force `isolation: "shared"` whenever `target.environmentId` names
a linked environment.

## Files, vaults and Markdown conversion

Keep Git repositories under `~/Repos/`, knowledge vaults under `$VAULTS_ROOT`,
and iterative renders, previews, screenshots and throwaway exports in
`~/Scratch/YYYY-MM-DD/<slug>/` until accepted. Never nest a Git repository
inside a synced vault. Keep the Desktop empty. Use `/tmp/` for mechanical
scratch.

Search indexed vaults through your search MCP server or CLI (such as QMD)
before grepping files on disk. Reserve `rg` and `grep` for source code
repositories, exact regex matches or unindexed folders.

Put accepted deliverables at the requested destination and keep rebuild sources.
Name generated artefacts `YYYY-MM-DD Title.ext` using the build date. Preserve
raw evidence filenames. Keep working output outside skill repositories.

Convert recurring source material (PDFs, office decks, spreadsheets, web pages)
into clean Markdown before repeated agent reads, or clean HTML where visual
layout carries meaning. Keep raw originals intact in `raw/` or beside the
converted file.

## Boundaries

- **Boundary Rule.** Confidential project, client or employer material stays
  inside its designated vault or repository. Never copy it into personal vaults,
  global instructions or public repositories.
- **Leaving Test.** Every project or work vault must remain complete and usable
  if handed over without your personal Home Repo or private skills.

## Session continuity and handoff

Start non-trivial work with `$AGENT_NOTES/Sessions/YYYY-MM-DD <slug>.md`.
Use a three-to-five-word lowercase slug. Update today's existing note for the
same goal. Read the destination's instructions before writing.

Include YAML frontmatter fields for `agent:`, `host:`, `status:` and `started:`.
Set `agent:` to the agent runtime. Set `host:` to `cmux`, `t3-code` or `cli`.
Record the goal, decisions, files and next step. Update the note at milestones.
Close with `ended:` and `## Outcome`. Use one of these status values:

- `queued`
- `in-progress`
- `review`
- `done`
- `blocked`
- `failed`

At 30% context usage or about 300k tokens, whichever comes first, interactive
coordinators and long-lived top-level threads finish the current step and hand
off before compaction. Bounded `delegate_task` children and workflow workers
are exempt and complete their single ticket. Save a dated brief under
`$AGENT_NOTES/Sessions/Handoffs/`. Include the goal, decisions, changed files,
evidence and next step. Use `/orchestrator` when dispatching across workspaces
or threads. Respect the host's rules for creating a successor. If context usage
is unavailable, say so and plan continuation between phases.

## Secrets and commits

Read secrets at runtime from the OS keychain or a CLI password manager. Never
commit secrets or paste credentials into tracked files, prompts or notes. Scan
durable output for credentials and private data before saving it.

Stage named files. Keep hooks enabled. Make one logical change per commit.
Use an imperative subject under 70 characters. Verify completion against the
request and report evidence with any unverified checks.
