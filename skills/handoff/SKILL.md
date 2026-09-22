---
name: handoff
version: 1.0.0
description: >-
  Transfer session context. Use for handoff, pickup prompts, parking notes or auto-spawning a cmux workspace.
fallback: If clipboard or cmux tooling is unavailable, write the handoff prompt under $AGENT_NOTES/Sessions/Handoffs/ and report the path.
---

# Handoff

Transfer work context between agent sessions without losing progress.

**Requires** the `cmux` skill (its `spawn-workspace.sh`) for the auto-spawn mode
only. Clipboard and park modes have no external dependency. Where
`spawn-workspace.sh` is unavailable, fall back per the `fallback:` rule above:
write the prompt under `Sessions/Handoffs/` and report the path.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/`, handoff briefs in `Sessions/Handoffs/` |

When this skill writes `<session-path>` it means a file under
`$AGENT_NOTES/Sessions/` named `YYYY-MM-DD <title>.md`. Every harness - Claude
Code, Codex, cmux - writes its handoff artefacts to the same place, and the
`agent:` frontmatter field says which one wrote it. Do not write pickup prompts,
continuation prompts or session-history summaries to the Desktop.

## Intake

One panel, only where the request leaves the mode open. `handoff` or `handover`
alone spawns a new workspace; `park` parks; `clipboard` or `copy` copies; a
running workspace named as the receiver is a live delivery. A request naming
none of these asks. Skip what the request settles; say what you read in the line
above the panel.

**Mode** - How is the brief delivered?
- New workspace - the brief written under `Handoffs/`, then `spawn-workspace.sh` (`workflows/auto-spawn.md`)
- Clipboard - the brief written under `Handoffs/`, then copied to the clipboard (`workflows/immediate.md`)
- Park - the full Progress entry on the session note; nothing else (`workflows/park.md`)
- Live peer - `cmux send` into a running workspace's input, then Enter
- settled by: "handoff" or "handover" alone (New workspace); `park` (Park); "clipboard" or "copy" (Clipboard); a running workspace named (Live peer)

**Session** - Which record?
- This session - the active session note under `Sessions/`
- Named note - a session note you name after the panel
- Conversation only - no note; the brief drawn from this conversation
- settled by: an open session note for this workspace (This session)

**Focus** - What does the successor do first?
- Stated priority - the next step you name after the panel
- Continue - where the work stopped, from the Progress line
- Verify first - the inherited premises re-checked live before anything is built
- settled by: a priority in the request (Stated priority)

Text fields, one message after the panel: the priority, the note name, and the
workspace name where Mode is Live peer. The seat, model and effort come from the
routing canon, never from a question. Step 5 of `workflows/auto-spawn.md` names
the tier and the helper resolves it. A model the user names in the request wins
and is logged as named.

## Workflow routing

**The file is the handoff.** Every mode leaves a durable file before anything
volatile: the brief at `$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md` for
Clipboard and Auto-spawn, and the Progress entry in the session note for Park.
The clipboard and the spawned workspace are two ways of delivering a brief that
already exists on disk. A clipboard copy reporting success is not delivery: the
pasteboard is volatile, and a handoff is usually written because the application
holding it is about to restart.

Choose the delivery that fits the user's intent. Three modes:

| Trigger | Mode | Delivery |
|---|---|---|
| `/handoff` (default) | Clipboard - `workflows/immediate.md` | write the brief under `Handoffs/`, copy it to the clipboard, then report the path first and the clipboard second |
| `/handoff park` | Park - `workflows/park.md` | append the full Progress entry to the session note and stop |
| `/handoff to a new session` / `to a new workspace` / `and open it` | Auto-spawn - `workflows/auto-spawn.md` | write the brief under `Handoffs/`, name the tier, run `spawn-workspace.sh --tier <letter> --prompt-file "$PROMPT_FILE"`, quote the route line it prints, return the workspace name |

**Routing rule:** scan the user's `/handoff` arguments for the phrases `to a new
session`, `to a new workspace`, or `and open it`, in any case. If one is
present, route to Auto-spawn - do NOT stop at clipboard. Clipboard is the
default when no trigger appears; Park needs the explicit `park` argument.

**Never clipboard alone when a restart is in play.** If the handoff exists
because the terminal, the machine or the session is being restarted, write the
brief to `Handoffs/` and name that path in the reply. Clipboard-only in that
case loses the brief at the moment it is needed. Where the brief was built in a
heredoc and only the pasteboard holds it, recover it to the file before
reporting anything.

## Progress entry format

**Immediate** handoffs write a minimal session entry, because the handoff prompt
carries the full detail:

```markdown
### YYYY-MM-DD (handoff)
Exported the PNGs, wrote the agenda, published to the wiki. Stopped at: announcement not posted. See the handoff for full context.
```

**Park** handoffs write the full entry to session Progress, because the session
file IS the handoff:

```markdown
### YYYY-MM-DD (parked)
**Done:** What was accomplished. Concrete, and not vague.
**Learned:**
- Gotchas, constraints and decisions discovered during the work
**Stopped at:** Exactly where work paused.
**Next:**
1. First thing to do when resuming
2. Second action
**Files:**
- `path/to/file.md` - what it is
```

**Why the split:** a long-running session accumulates many Progress entries, and
each full entry adds about thirty lines. After six to eight handoffs the session
file grows too large to read. Immediate handoffs transfer the detail through the
brief file, keeping the session note lean. Park handoffs are for work that might
not resume soon, where the session note is the persistent record.

## Key rules

- **Handing off to a live workspace is an active delivery, and not a dead-drop
  file.** Where the receiver is an already-running cmux workspace - a peer agent
  mid-task, rather than a new session - deliver into its input: `cmux send
  --workspace <id> "<message>"` then `cmux send-key --workspace <id> Enter`, and
  confirm it landed in that workspace's queue. A shared findings file is a
  durable record and NOT a notification: the peer can finish its run without
  ever reading it. Log to the file AND message the live peer. Writing only to
  the file and reporting "relayed" is the failure mode.
- **Update the docs first.** The project is the source of truth, and not the
  clipboard.
- **The user's direction beats the agent's analysis.** Where the user said what
  to focus on next, that is the priority.
- **Progress is handoff data.** The same structure everywhere, in one canonical
  location.
- **Scan for pending markers before Next Steps.** Grep for `USER-COMMENT`,
  `NEEDS USER INPUT`, `TODO` and `FIXME` in the active session's files. Every
  marker found must appear explicitly in the handoff's Next Steps with where it
  lives, what is being asked, and who must act.
- **Reference, and do not duplicate.** Where content already lives in a spec, a
  plan, an ADR, an issue, a commit, a diff or a note, link the path or the URL
  instead of pasting the content. The handoff is a pointer document and the
  source stays canonical. Inline a quoted excerpt only where it is load-bearing
  for the next session's first move.
- **Redact secrets and personal data.** Before writing the handoff, scan for API
  keys, tokens, passwords, OAuth client secrets, private keys and personally
  identifiable information. A prompt file is persistent, so assume handoff
  contents are durable and shareable.
- **Suggest skills for the receiver.** Include a Suggested Skills block in every
  clipboard or prompt-file handoff. The receiver picks up cold and benefits from
  being told which one to three skills are likely to apply on the first action.
- **Handing off a *role* makes its skill mandatory, and not suggested.** Where
  the successor inherits a named seat - orchestrator, or any other role with a
  skill governing how it behaves - the very first line of the handoff instructs
  it to load that skill before acting: **"You are the orchestrator. Load the
  `orchestrator` skill before you touch the fleet - this brief carries the
  state, the skill carries the rules."** A brief carries what is true right now;
  the skill carries how the seat is meant to operate, and the two are not
  interchangeable. One orchestrator successor ran an entire seat from an
  inherited brief without loading the skill, and broke rules already written in
  it. A Suggested Skills block further down the file is too weak to prevent
  this, so put the instruction first and in the imperative.
- **Verify inherited premises.** Tag every infrastructure, topology or
  file-location claim in a handoff as VERIFIED (with the proving command) or
  ASSUMED, and re-confirm any load-bearing claim with a live check before
  building on it. Treat an inherited model as a hypothesis until confirmed. See
  `references/verify-inherited-premises.md`.
- **Two agents on different machines** coordinate through a split-by-writer
  bridge pair, and never a shared file. See `references/cross-machine-bridge.md`.

## Mode workflows

Each mode's step-by-step procedure lives in its own workflow file. Route with
the table above, then read the matching file:

- **Clipboard (default)** → `workflows/immediate.md`
- **Auto-spawn** → `workflows/auto-spawn.md`. Needs the `cmux` skill.
- **Park** → `workflows/park.md`

All three share the Progress Entry Format and Key Rules above, and the
pending-marker scan below.

## Before writing Next Steps: scan for pending markers

**Always** grep the active session's content, plan and research files for
pending-review markers BEFORE drafting the Next Steps list. Do not let them
carry forward silently between sessions.

```bash
grep -nH 'USER-COMMENT\|NEEDS USER INPUT\|TODO\|FIXME\|NEEDS CLARIFICATION' \
  "${AGENT_NOTES:-$HOME/agent-notes}"/Sessions/*.md
```

Every marker found must appear explicitly in the handoff's Next Steps or Open
Items section with:

- **Where** it lives (file:line, or the section name)
- **What** is being asked (one line, from the marker text itself)
- **Who** must act (does the user need to approve, or should the agent proceed?)
