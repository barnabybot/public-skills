# Worker behaviour

Use the model and effort from the table in `SKILL.md`. Task boundaries and
escalation are in `references/routing-rules.md`.

**These are your notes to write.** The list below is the portable half: things
true of coding agents generally. Everything model-specific belongs here too,
and only you can write it, because it describes the models in your table.
Keep it as a list of observations with the evidence attached, so a later reader
can tell a measurement from a habit.

## Portable

- **Long quiet turns are normal** on a large model at high or max effort.
  Diagnose a stalled seat from an idle input line AND a final message that
  promises action with no tool call after it. Both tells, or it is still
  working. Send an authorised continuation once that state is verified.
- **Include this instruction in every dispatch brief**, verbatim: "Before
  reporting progress, audit each claim against a tool result from this session.
  Only report work you can point to evidence for; if something is not yet
  verified, say so explicitly."
- **Carry intent.** State the larger task, the intended reader, and what the
  output enables.
- **Succession is the orchestrator's call.** A seat with a fixed context window
  keeps working at full quality until asked to hand off. A seat that compacts in
  place continues through compaction and recycles on a new phase.
  `workflows/recycle.md` carries the thresholds.
- **Cap a seat's own delegation.** Delegated work inherits the parent model
  unless told otherwise, so a seat that fans out freely bills its subagents at
  its own rate. Say "do this yourself; delegate only if a track is large and
  genuinely independent", and name the model explicitly for delegation that
  needs judgement.
- **Give a literal seat the complete file list.** Where results are thin,
  investigate the brief before escalating effort.
- **Ask reviewers for every finding** with a confidence and an estimated
  severity, then filter yourself. "Only report high-severity issues" gets
  followed literally: the same depth, fewer findings.
- **Report coverage with the findings.** A zero is a measurement of what the
  instrument looked for. A zero with no stated non-coverage is not reportable.
- **Accept the artefact.** Where a worker wrote a file, read the file. Do not
  ask it to paste the contents into chat.

## Yours to fill in

One line per model in your table. The shape that has held up elsewhere:

- Which models spin at high effort and should start lower.
- Which model gains nothing from max, so a stall there changes model rather
  than effort.
- Which models need a locked plan and testable acceptance before they are
  useful.
- Which model's CLI takes which effort vocabulary, where it differs from the
  `efforts` list in `references/routing-metadata.yaml`.
- Any environment variable a seat needs at launch. For a Claude seat, for
  example, `CLAUDE_CODE_SUBAGENT_MODEL` sets the default model its subagents
  use.
