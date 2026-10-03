# Clipboard handoff

Use only for an explicit copy or clipboard request.

1. Prepare the brief using `workflows/handoff.md` and save it under `$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md`.
2. Run `pbcopy < "$PROMPT_FILE"` using that saved path.
3. Report the file path and whether the copy succeeded. If clipboard access fails, the file remains the delivery artefact.
