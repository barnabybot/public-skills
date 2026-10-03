# Park

Use only when the user explicitly asks to park the session.

Update the session note's Progress with completed work, findings, stopping point, next actions and file paths. Put the user's next priority first. Record unresolved decisions and current authorisation. The note carries the full context for later resumption.

Close the session record with `status: done`, `ended:` and an Outcome that states the work was parked and identifies what remains. Report the note path. A later session reads that note before continuing.

This deliberately removes the parked session from active dashboard groups. `done` closes the session record; the Outcome must state that work remains and where to resume. Use `blocked` only when an active session is waiting for a decision or dependency.
