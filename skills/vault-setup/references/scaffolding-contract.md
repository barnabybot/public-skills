# Vault scaffolding contract

Why these five vault types exist, the shared nine-step scaffolding contract, non-Markdown state rules, exclusions and post-scaffold steps.

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
4. **Write AGENTS.md.** Read `templates/<type>/AGENTS.md.tmpl`. Resolve every
   token using the shared inputs and the selected workflow's derived values.
   Use search-and-replace with no template engine. Write `$VAULT/AGENTS.md`.
5. **One instruction file.** Keep `AGENTS.md` as the canonical instruction
   file. For Claude Code, create a relative symlink at the vault root with
   `ln -s AGENTS.md "$VAULT/CLAUDE.md"`. Other hosts can use the same alias
   where needed. Both names must resolve to the same file.
6. **Write log.md** from `templates/<type>/log.md.tmpl`. Resolve every token
   using the shared inputs and the selected workflow's derived values.
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
   instruction file has another name or another location. Confirm every output
   template token has been resolved.
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
| Check the instruction file | Open `$VAULT/AGENTS.md` and adapt it to the vault |

## Related

- Type workflows: `workflows/{personal,projects,operations,agents,wiki}.md`
- Per-type templates: `templates/<type>/`
- The `agents` type pairs with the `orchestrator` and `recall` skills
  in this repository, which write into exactly the tree it scaffolds.
