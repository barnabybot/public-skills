---
name: vault-setup
version: 1.0.0
description: >-
  Set up a Markdown knowledge vault. Use for a new personal, projects, operations, agents or wiki vault, scaffolding, templates or search registration.
fallback: >-
  Step 7 is already conditional, so a missing search tool collapses to
  `REGISTER_SEARCH = no` - scaffold the vault, set `{{SEARCH_REGISTERED}}` in
  log.md accordingly, drop the collection check from step 8's verify, and tell
  the user at step 9 that registration is outstanding. The tree and AGENTS.md
  need only `mkdir` and a file write. If `date` is unavailable, supply
  `CREATED` from the session date rather than leaving the template token
  unsubstituted.
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Write
  - Edit
  - AskUserQuestion
---

# vault-setup

Create a Markdown knowledge vault: folder tree, root `AGENTS.md` and starter
templates. [Obsidian](https://obsidian.md) opens any folder as a vault, though
nothing in the output depends on Obsidian. Type variants live in
`workflows/<type>.md` with templates in `templates/<type>/`.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `VAULTS_ROOT` | `~/vaults` | Parent folder for new vaults (or pass a full path when asked) |

## Intake

One panel, before any other read. Skip what the request settles; say what you
read in the line above the panel. The chosen type's `workflows/<type>.md` is
read after the panel; its own choices form one further panel and its text fields
one message, and never one question per turn.

**Type** - What kind of vault?
- Personal - a personal knowledge base: clippings, references, daily notes (`workflows/personal.md`)
- Projects - a time-bounded project: cockpit, planning, delivery, reporting and meetings (`workflows/projects.md`)
- Operations - how a team runs: methods, proposals, meeting records and internal delivery (`workflows/operations.md`)
- System-maintained - an agents vault or an LLM-maintained wiki; the Kind question in step 1 picks which
- settled by: a named type; a project or code name (Projects); a team or function (Operations); "wiki" (System-maintained, Wiki); "agents", "sessions", "handoffs" or "runtime" (System-maintained, Agents)

**Search** - Register the vault with a search index?
- Now - add the collection and embed it, so the vault is searchable from the first note
- Later - scaffold only; register it when you are ready
- settled by: "no search" or "register later" (Later); a host with no search tool (Later, per `fallback:`)

**Files** - What will the vault hold?
- Markdown only - notes alone; the per-device sync toggles stay at their default and step 9 is skipped
- Mixed - workflows will write JSON or JSONL ledgers, spreadsheets or HTML renders; step 9 sets the sync toggle on every device and records each in `log.md`
- settled by: "ledger", "spreadsheet" or "renders" in the request (Mixed)

**Writes** - When do I create it?
- Show first - print the path, tree and substitutions, and wait for a go at step 2
- Create now - skip the step 2 confirmation; the tree, `AGENTS.md` and `log.md` land at once
- settled by: "just create it" or "go ahead" (Create now)

Text fields, one message after the panel: the vault name and its one-sentence
purpose, plus the search collection name only where it differs from the
lowercased vault name. The type workflow's own fields (structure axis, domain
sentence, agent folders, seed lists) follow from its input section in the same
way.

## Step 1 - Choose the vault type

Type comes from the Intake panel above. Five types exist and a question holds
four options, so the System-maintained answer asks one more question, alone,
before any workflow is read. Skip it where the request settles it.

**Kind** - Which system-maintained vault?
- Wiki - a three-layer base: `raw/` sources, LLM-compiled Concept, People and Book pages, hubs, `schema.md`; lives beside the skill that reads it (`workflows/wiki.md`)
- Agents - what every session from every tool writes down: session notes, handoffs, audits and per-agent state (`workflows/agents.md`)
- after: Type
- settled by: "wiki" (Wiki); "agents", "sessions", "handoffs" or "runtime" (Agents)

Read the matching `workflows/<type>.md` once the type is known:

| Vault type | Workflow | Use when |
|---|---|---|
| personal | `workflows/personal.md` | A personal knowledge base - clippings, daily notes, references |
| projects | `workflows/projects.md` | A time-bounded project - cockpit, workstreams, meetings, deliverables |
| operations | `workflows/operations.md` | Continuing team operations - methods, proposals, meeting records, internal delivery |
| agents | `workflows/agents.md` | Every tool's runtime record - flat sessions, handoffs, audits, per-agent state |
| wiki | `workflows/wiki.md` | An LLM-maintained knowledge base, beside its skill or standalone |

Each workflow supplies its input set, folder tree, and `templates/<type>/`.
Read [`references/scaffolding-contract.md`](references/scaffolding-contract.md)
for the five-type rationale, the shared nine-step scaffolding contract,
non-Markdown state rules and post-scaffold setup.
