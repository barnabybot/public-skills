# Park workflow

Update the session Progress only. No clipboard. The session file IS the handoff
for later resumption. Needs the explicit `park` argument.

## Why this works

The session note already has Goal, Context, Progress and Definition of Done. A
separate handoff artefact duplicates this, which makes two sources of truth, and
one of them goes stale. The Progress Entry Format gives the session note the
same bones as a clipboard handoff. Next time work resumes, the agent reads the
session file and picks up from Progress.

## Steps

1. **Find the active session.** Check for the `status: in-progress` session
   worked on in this conversation. If the user named one, use that.

2. **Update the session Progress section.** Append a new entry using the
   Progress Entry Format in `SKILL.md`. Factual, and not verbose.

3. **Capture the user's direction.** Where the user gave a specific intention
   for the next session, put that first in Next. Their words beat the agent's
   analysis.

4. **Confirm:**

   > Session updated: `<path>`.
   >
   > To resume: reopen the session when ready.
