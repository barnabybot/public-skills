# Agents vault - scaffold workflow

Creates an agents-type vault at `${VAULTS_ROOT:-$HOME/vaults}/<NAME>/`: the place where every session from every tool writes down its work. It holds session notes, handoffs, audits, per-agent state and the evidence skills write about their own builds. Agents write here on every tick, so the boundary rules in the template are part of the runtime contract.

This skill is fully self-contained. Every template lives in `../templates/agents/`.

## Inputs

Choices, one panel after the Intake panel. These are the type-specific
follow-ups described in the shared contract. Offer the defaults below; apply
them when the user accepts defaults. An unanswered panel stays pending.

**Fleet docs** - Do workstations run against this vault?
- Yes - create `Workstations/` (Setup, Skills, Tools, References, Plans, Templates, Provisioning) for workstation setup notes, the generated skills index and per-host inventories
- No - server-side agents only; skip `Workstations/`
- settled by: "server only" or "headless" (No)

**Secrets** - Does an agent read credentials from this vault?
- Yes - create `Secrets/` for one encrypted credentials file; inject its password at runtime and keep it separate from the vault
- No - agents read the host's secrets store directly
- settled by: "no secrets" (No)

Text fields, one message: `ECOSYSTEM_NAME` (one phrase describing the agents,
e.g. `laptop + build server`) and `AGENT_DIRS` (comma-separated, one top-level
folder per agent that writes state). Offer these defaults in the same message.

| Input | Default | Stored value |
|---|---|---|
| Fleet docs | Yes | `INCLUDE_WORKSTATIONS_DIR=yes`; No sets `no` |
| Secrets | No | `SECRETS_DIR=no`; Yes sets `yes` |
| `ECOSYSTEM_NAME` | `local agents` | Use the supplied phrase or this default |
| `AGENT_DIRS` | The current session's agent ID, e.g. `codex` or `claude-code` | Comma-separated IDs; ask for an ID if the host does not identify itself |

Normalise each agent ID before writing: trim whitespace, lowercase, and replace
internal spaces with hyphens (`Claude Code` becomes `claude-code`). IDs use
letters `a-z`, digits and single hyphens between words. Reject path separators,
empty entries and IDs that collide with the fixed root folders, ignoring case.
Store the normalised list in `AGENT_DIRS`; use the same IDs in the tree, tables,
log and `agent:` fields. Shared folders retain the casing shown below.

If Secrets is Yes and Files is Markdown only, ask the user to revise one of
those answers before writing: an encrypted credentials file requires Mixed.

Fixed by the Agents pattern, so no question: session notes file flat at `Sessions/` root with `agent:` frontmatter identifying the source, so a query tool can group on it; audits sit per agent under `Audits/<agent>/` with cross-agent synthesis at `Audits/` root; `Ops/` holds skill evidence; search registration stays off unless the Intake panel said Now, because agents read these files by direct access. `VAULT_NAME`, `VAULT_PURPOSE`, `SEARCH_COLLECTION` and `CREATED` come from the shared contract.

## Output structure

```
${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/
├── AGENTS.md
├── CLAUDE.md -> AGENTS.md        when the host needs this alias
├── log.md
├── <agent>/                     lowercase ID from AGENT_DIRS; runtime state, machine-managed
│   ├── config/                  the agent's own instruction and memory files
│   ├── ops/                     usage logs, snapshots, health series
│   ├── sessions/                per-run session files
│   └── skills/                  skill files the agent reads directly
├── Workstations/                (Fleet docs = Yes)
│   ├── Setup/                   workstation setup notes
│   ├── Skills/                  generated skills index
│   ├── Tools/                   per-tool reference
│   ├── References/              tool and memory reference notes
│   ├── Plans/                   workstation engineering plans
│   ├── Templates/               note templates
│   └── Provisioning/            per-host tooling inventories
├── Sessions/                    flat session notes, YYYY-MM-DD <slug>.md
│   ├── Handoffs/                pickup prompts
│   └── Archive/
├── Audits/                      cross-agent synthesis at root
│   └── <agent>/                 per-agent audits
├── Ops/                         skill evidence: journals, current-state reports, Ops/<name>/ corpora
└── Secrets/                     (Secrets = Yes)
```

## Workflow

Run the shared scaffolding contract in [`../SKILL.md`](../SKILL.md). This workflow supplies the type-specific pieces below.

- **Inputs**: resolve the choices and normalise `AGENT_DIRS` as above before
  running the folder block in Bash or zsh.
- **Folder tree** (step 3):
  ```bash
  VAULT="${VAULTS_ROOT:-$HOME/vaults}/$VAULT_NAME"
  mkdir -p "$VAULT"/{Sessions/{Handoffs,Archive},Audits,Ops}
  if [ "$INCLUDE_WORKSTATIONS_DIR" = "yes" ]; then mkdir -p "$VAULT/Workstations"/{Setup,Skills,Tools,References,Plans,Templates,Provisioning}; fi
  if [ "$SECRETS_DIR" = "yes" ]; then mkdir -p "$VAULT/Secrets"; fi
  # zsh does not word-split an unquoted variable, so read the list rather than
  # looping over it - a for-loop here runs once, over the whole string.
  echo "$AGENT_DIRS" | tr ',' '\n' | while IFS= read -r ag; do
    ag="$(echo "$ag" | sed 's/^ *//;s/ *$//')"
    [ -n "$ag" ] && mkdir -p "$VAULT/$ag"/{config,ops,sessions,skills} "$VAULT/Audits/$ag"
  done
  ```
- **Templates** (steps 4 + 6): `../templates/agents/AGENTS.md.tmpl` and
  `../templates/agents/log.md.tmpl`. Each complete token list follows. Substitute
  every token, including an empty string for an omitted optional row.

  **AGENTS.md tokens:**
  - `{{VAULT_NAME}}`, `{{VAULT_PURPOSE}}`, `{{CREATED}}` - shared inputs
  - `{{ECOSYSTEM_NAME}}` - the resolved phrase above
  - `{{TOP_LEVEL_FOLDERS_LIST}}` - one bullet per top-level folder created, bold name then its role in one sentence, in the order of the tree above
  - `{{AGENT_UNIVERSES}}` - one `### <agent>` heading per agent folder with a four-row table (`config/`, `ops/`, `sessions/`, `skills/`) carrying a contents cell and a retention cell of `tbd - set policy`; use the roles in the tree above
  - `{{WORKSTATION_SETUP_ROW}}` - Fleet docs Yes: ``| Workstation setup note | `Workstations/Setup/` |``; No: empty string
  - `{{SECRETS_DIR_DESCRIPTION}}` - Yes: "`Secrets/` is reserved for one encrypted credentials file; setup leaves it empty. Its password is injected at runtime on the host that reads it and stays separate from the vault." No: "Agents read credentials from the host's secrets store directly."
  - `{{SEARCH_INDEXED}}` - `false` until registration is verified, then `true`
  - `{{SEARCH_INDEXED_DESCRIPTION}}` - "read by direct file access" until registration is verified, then "search-indexed; collection `<name>`"

  **log.md tokens:**
  - `{{VAULT_NAME}}`, `{{CREATED}}`, `{{ECOSYSTEM_NAME}}` - resolved inputs
  - `{{AGENT_DIRS_LIST}}` - the normalised comma-separated IDs in `AGENT_DIRS`
  - `{{INCLUDE_WORKSTATIONS_DIR}}` - `yes` or `no`, matching Fleet docs
  - `{{SECRETS_DIR_ENABLED}}` - `yes` or `no`, matching `SECRETS_DIR`
  - `{{SEARCH_INDEXED}}`, `{{SEARCH_REGISTERED}}` - initially `false` and `no`; after step 7, append the verified result to the log and update the search fields in `AGENTS.md`
  - `{{SYNC_STATUS}}` - Markdown only: "Skipped: Markdown only." Mixed: "Pending: record each device after step 9." After step 9, append the devices actually configured to the log; if no sync service is used, append "Not configured: no sync service in use."

  `SEARCH_COLLECTION` supplies the collection name in the search description;
  it is not a template token in these two files.
- **Verify** (step 8): confirm `vault_type: agents`, the exact tree for the
  selected options and each agent's four subfolders. The root allowlist and
  filing table must describe only the folders created. If `CLAUDE.md` exists,
  confirm it is a symlink to `AGENTS.md`. Run `grep -rn '{{' "$VAULT"` and
  resolve every match. Exit code 1 with no output means no unfilled tokens.

### Type-specific notes

- **Search registration is usually off.** Agents read these files by direct access. Register only where the Intake panel said Now; the collection name defaults to the lowercased `VAULT_NAME`.
- **Sync toggles follow the Files answer.** Markdown only skips step 9 and
  records that in `log.md`. Mixed applies step 9 on every device using a sync
  service. Empty runtime folders do not require Mixed. Before adding JSON,
  images, encrypted credentials or other non-Markdown files later, update the
  Files choice and complete step 9. Record unavailable devices as pending.
- **The final report** (step 10) restates the cross-vault boundary rule, tells the user to set `AGENT_NOTES` to the vault root in `~/.zshenv` (the orchestrator, cmux and recall skills write `Sessions/`, `Sessions/Handoffs/` and `Ops/` beneath it), and reminds the user to point every scheduled writer at the new per-agent paths and to give each output folder a retention row before its job goes live.
- This workflow creates the vault scaffold. Agent configuration, server runtime stores, credential-manager setup and scheduled-job mirrors are separate work.

### Worked example

For a Claude Code session, the user chooses Agents, Search Later, Files Markdown
only and Writes Create now, then accepts the type-specific defaults. They name
the vault `agents` with purpose "Record agent sessions and handoffs."

Use `ECOSYSTEM_NAME=local agents`, `AGENT_DIRS=claude-code`,
`INCLUDE_WORKSTATIONS_DIR=yes` and `SECRETS_DIR=no`. With no `VAULTS_ROOT`
override, create `$HOME/vaults/agents/` with `AGENTS.md`, `log.md`, the relative
`CLAUDE.md` symlink, `claude-code/{config,ops,sessions,skills}`,
`Audits/claude-code/`, `Sessions/{Handoffs,Archive}`, `Ops/` and the seven
`Workstations/` subfolders shown above. Omit `Secrets/`.

Substitute the complete token lists above with today's `CREATED` date. Search
values are `false`, `no` and "read by direct file access"; the log records
"Skipped: Markdown only." Verify the tree, symlink and empty token scan. Report
the created files and skipped search/sync steps, then tell the user to set
`AGENT_NOTES` to `$HOME/vaults/agents` in `~/.zshenv` and open the vault in their
editor. Scheduled writers remain unconfigured.

## Template files (self-contained)

| File | Path | Role |
|---|---|---|
| AGENTS.md template | `../templates/agents/AGENTS.md.tmpl` | Full agents-vault contract: vault-root rule, where-things-go table, agent folders, flat sessions with the closed `status:` vocabulary, audits, `Ops/`, secrets, retention, the boundary rule, maintenance entrypoints |
| log.md template | `../templates/agents/log.md.tmpl` | Initial runtime-log entry recording the scaffold |
