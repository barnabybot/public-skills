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

One skill for creating a Markdown knowledge vault: the folder tree, the
instruction file and the starter templates for its type.

A "vault" here is a folder of Markdown files with an `AGENTS.md` at its root
telling any agent how to work inside it. [Obsidian](https://obsidian.md) opens
one with *Open folder as vault*, and nothing in the output depends on Obsidian -
it is Markdown and folders.

This skill owns the shared scaffolding contract below. The five type variants
live as sub-workflows in `workflows/<type>.md`, with per-type templates in
`templates/<type>/`.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `VAULTS_ROOT` | `~/vaults` | The parent folder new vaults are created under |

Set it to wherever you keep them. A single vault can also be created anywhere by
naming the full path when the skill asks.

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

Each workflow supplies three things only: its **input set**, its **folder
tree**, and its **AGENTS.md plus starter templates** (under
`templates/<type>/`). Everything below is shared across all types.

### Why these five

`projects` and `operations` are the pair worth explaining, because they look
alike and are not.

A **projects** vault is time-bounded and ends. It has phases, a delivery date,
deliverables that get signed off, and a close-out. When the project ends the
vault stops growing and becomes a record. Its cockpit exists so somebody
returning after two weeks can see status in one screen.

An **operations** vault has no end. It holds how a team works: the methods it
reuses, the proposals it writes, the meetings it keeps having. Nothing in it
gets signed off and archived, so it needs maintenance rather than a cockpit,
and its value is in what gets reused across projects.

The tell is the question "when is this done?". A projects vault has an answer.
An operations vault does not.

## The shared scaffolding contract

Every vault scaffold runs these steps. The chosen workflow fills in the
type-specific tree and template; the procedure is identical.

1. **Gather the remaining inputs** per the workflow's input table: its choices
   as one panel, its text fields in one message, never one per turn. The Intake
   panel has settled the type and `REGISTER_SEARCH`. Always collect
   `VAULT_NAME`, `VAULT_PURPOSE` and `SEARCH_COLLECTION` (default: the
   lowercased `VAULT_NAME`). Set `CREATED` to `date +%Y-%m-%d`.
2. **Confirm the plan.** Print the proposed vault path, the folder tree, and the
   variable substitutions back to the user. Wait for confirmation before writing
   unless Writes was Create now in the panel.
3. **Create the folder tree.** `mkdir -p` the workflow's type-specific tree at
   `$VAULT`. `$VAULT` is `${VAULTS_ROOT:-$HOME/vaults}/$VAULT_NAME` for every
   type except a wiki beside its skill, where the wiki workflow sets it.
4. **Write AGENTS.md.** Read `templates/<type>/AGENTS.md.tmpl`, substitute
   `{{VAULT_NAME}}`, `{{VAULT_PURPOSE}}`, `{{SEARCH_COLLECTION}}` and
   `{{CREATED}}` by search-and-replace with no template engine, and write it to
   `$VAULT/AGENTS.md`.
5. **One instruction file.** `AGENTS.md` at the vault root is the instruction
   file for every host: Codex reads it by name, and Claude Code reads it when no
   `CLAUDE.md` is present. Where a host needs `CLAUDE.md`, symlink it to
   `AGENTS.md` rather than writing a second file - a second file is a second
   copy to keep in step.
6. **Write log.md** from `templates/<type>/log.md.tmpl`, substituting
   `{{VAULT_NAME}}`, `{{CREATED}}`, `{{SEARCH_COLLECTION}}` and
   `{{SEARCH_REGISTERED}}`.
7. **Register the search collection** where `REGISTER_SEARCH = yes`. The shape
   depends on your tool. For [QMD](https://github.com/qmd-sh/qmd):

   ```bash
   qmd collection add "$VAULT" --name "$SEARCH_COLLECTION" --mask "**/*.md"
   qmd update
   qmd embed -c "$SEARCH_COLLECTION"
   ```

   Where you use something else, register it however that tool expects, and say
   in the report which tool you used.
8. **Verify:** `AGENTS.md` is present, `vault_type: <type>` is declared inside
   it, and - where registered - the search collection lists. Any tool that
   discovers vaults by walking for `AGENTS.md` cannot see a vault whose
   instruction file has another name or another location.
9. **Set the sync file-type toggles on every device** where Files was Mixed in
   the panel: the workflows for this vault will write non-Markdown state. See
   below. This step is skipped only for a vault that will hold Markdown and
   nothing else.
10. **Report:** the vault path, the files created, the search status, the sync
    toggles set, and the next step - open `$VAULT` in your editor.

### Non-Markdown state and per-device sync toggles

**A sync service's file-type toggles are usually per device, and the default is
often Markdown only.** Enabling "sync all other types" on one machine makes that
machine *upload*. Every other device keeps ignoring those files until its own
toggle is flipped, and nothing reports the gap: sync is active, Markdown flows,
transfer lines appear in the journal. A vault can look healthy on every host
while its machine-generated state never leaves the machine that wrote it.

So at creation, for any vault whose workflows write non-Markdown state, set the
toggle **on every device that opens the vault** - each workstation and each
headless server peer - and record in the vault's `log.md` which devices were
done. Silence here does not mean "not yet configured". It means machine-local
state, with no warning.

**The case.** One vault diverged this way and it was found by accident, by
somebody reading a ledger for another reason. The vault held 325 Markdown files
on the workstation and 325 on the server, and 649 non-Markdown files on the
workstation against 1 on the server. The missing file was the JSONL ledger a
scoring tool reads, so the tool's output depended on which machine you sat at:
one host held the current data, the other a four-month-old copy that scored
every item as unrated. Nothing had failed, and nothing had warned.

Where you run more than one device against a vault, add a parity check that
counts non-Markdown files on each side and reports the gap.

## What scaffolding does NOT do

Copy content from an existing vault, configure your editor, set up automation,
or pre-populate `Templates/`. New vaults start empty.

## After scaffolding

| Need | Do |
|---|---|
| First filing audit | Walk the tree and check every note's frontmatter against the vault's `AGENTS.md` |
| Register search later | Add the collection with your search tool, then update and embed |
| Check the instruction file | Open `$VAULT/AGENTS.md` and edit it - it is a starting point, not a finished rulebook |

## Related

- Type workflows: `workflows/{personal,projects,operations,agents,wiki}.md`
- Per-type templates: `templates/<type>/`
- The `agents` type pairs with the `orchestrator`, `handoff` and `recall` skills
  in this repository, which write into exactly the tree it scaffolds.
