# Immediate handoff workflow (clipboard)

The default mode. Write the brief to a file, then copy it to the clipboard for
pasting into a new session.

## Steps

1. **Find the active session.** Check for the `status: in-progress` session
   worked on in this conversation. If the user named one, use that.

2. **Write a minimal progress entry.** The handoff brief carries the full
   detail:

   ```markdown
   ### YYYY-MM-DD (handoff)
   Exported the PNGs, wrote the agenda, published to the wiki. Stopped at: announcement not posted. See the handoff for full context.
   ```

   One sentence for done, one for stopped at. Nothing else. Learned, Next and
   Files live in the handoff brief.

3. **Capture the user's direction.** Where the user gave a specific intention
   for the next session, put that first in Next. Their words beat the agent's
   analysis.

4. **Write the brief to a file first.** The file is the handoff; the clipboard
   is one way of delivering it.

   ```bash
   NOTES="${AGENT_NOTES:-$HOME/agent-notes}"
   PROMPT_FILE="$NOTES/Sessions/Handoffs/$(date +%F) <slug>.md"
   mkdir -p "$(dirname "$PROMPT_FILE")"
   cat > "$PROMPT_FILE" <<'BRIEF'
   ## Continue: [brief title]

   **IMPORTANT: Before executing anything, present:**
   1. What you understand was done
   2. Your proposed next steps
   3. Wait for approval before acting

   ---

   ### Active session
   - `<path to the active session note>` (read this first - the Progress section is up to date)

   ### Context
   [From the session Goal and Context. 2-3 sentences.]

   ### Key learnings
   [From Progress > Learned]

   ### Current state
   [From Progress > Done and Stopped at]

   ### Next steps
   1. [The user's stated priority, where given]
   2. [From Progress > Next]

   ### Relevant files
   [From Progress > Files]

   ### Suggested skills
   [1-3 skills the receiving agent should consider on its first action, with a
   one-line reason each. For example: `/editorial-review` where a draft is
   mid-edit; `/recall` where the next session needs the history of a topic.]
   BRIEF
   ```

5. **Copy it.** On macOS, `pbcopy < "$PROMPT_FILE"`. On Linux, `xclip
   -selection clipboard < "$PROMPT_FILE"` or `wl-copy < "$PROMPT_FILE"`.

6. **Confirm, path first:**

   > Handoff written to `<path>`, and copied to the clipboard. Paste it into the
   > new session.

## Clipboard format rules

- **Assume no prior context.** The receiving agent knows nothing.
- **Files by path.** Give paths, and not editor-specific mentions.
- **MUST include the "wait for approval" instruction.** The new agent should not
  jump into execution.
- **Keep it concise.** Enough to continue, and not a novel.
