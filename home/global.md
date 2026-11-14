# Global steering

Read `<your-home-repo>/AGENTS.md` before cross-repo work or when locating a
project or vault. That file maps the Home Repo. This file supplies global rules.

## Skills and approval

Read a matching skill's `SKILL.md` before acting. Present its intake questions
first. Treat answers already supplied in the request as settled.

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

Let code carry its meaning. Keep comments for a necessary reason or external
constraint that code cannot express. Retain licences, shebangs, tool directives
and machine sentinels. Make the smallest change that meets the request.

## Files

Put accepted deliverables at the requested destination. Keep iterative renders,
previews, screenshots and throwaway exports in
`~/Scratch/YYYY-MM-DD/<slug>/` until accepted. Copy the accepted final artefact
to its destination. Keep rebuild sources. Use `/tmp/` for mechanical scratch.
Keep the Desktop empty.

Name generated artefacts `YYYY-MM-DD Title.ext` using the build date. Preserve
raw evidence filenames. Keep working output outside skill repositories.

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

Plan a handoff before 30% remaining context or about 300k tokens, whichever
comes first. The orchestrator skill uses an earlier limit of 30% context used
(70% remaining). Apply the earliest active limit. Finish the current step and save a dated brief under `$AGENT_NOTES/Sessions/Handoffs/`. Include
the goal, decisions, changed files, evidence and next step. Use `/orchestrator`
when installed. Respect the host's rules for creating a successor. If context
usage is unavailable, say so and plan continuation between phases.

## Secrets and commits

Read secrets at runtime from the OS keychain or a CLI password manager. Never
commit secrets or paste credentials into tracked files, prompts or notes. Scan
durable output for credentials and private data before saving it.

Stage named files. Keep hooks enabled. Make one logical change per commit.
Use an imperative subject under 70 characters. Verify completion against the
request and report evidence with any unverified checks.
