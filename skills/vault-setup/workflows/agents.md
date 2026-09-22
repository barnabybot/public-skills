# Agents vault - scaffold workflow

Creates an agents-type vault at `${VAULTS_ROOT:-$HOME/vaults}/<NAME>/`: the place where every session from every tool writes down its work. It holds session notes, handoffs, audits, per-agent state and the evidence skills write about their own builds. Agents write here on every tick, so the boundary rules in the template are part of the runtime contract.

This skill is fully self-contained. Every template lives in `../templates/agents/`.

## Inputs

Choices, one panel after the Intake panel:

**Fleet docs** - Do workstations run against this vault?
- Yes - create `Workstations/` (Setup, Skills, Tools, References, Plans, Templates, Provisioning) for workstation setup notes, the generated skills index and per-host inventories
- No - server-side agents only; skip `Workstations/`
- settled by: "server only" or "headless" (No)

**Secrets** - Does an agent read credentials from this vault?
- Yes - create `Secrets/` for one encrypted credentials file; inject its password at runtime and keep it separate from the vault
- No - agents read the host's secrets store directly
- settled by: "no secrets" (No)

Text fields, one message: `ECOSYSTEM_NAME` (one phrase naming the fleet, e.g. `laptop + build server`) and `AGENT_DIRS` (comma-separated, one top-level folder per agent that writes state).

Fixed by the Agents pattern, so no question: session notes file flat at `Sessions/` root with `agent:` frontmatter discriminating the source, because any dashboard over the folder groups on it; audits sit per agent under `Audits/<agent>/` with cross-agent synthesis at `Audits/` root; `Ops/` holds skill evidence; search registration stays off unless the Intake panel said Now, because agents read these files by direct access. `VAULT_NAME`, `VAULT_PURPOSE`, `SEARCH_COLLECTION` and `CREATED` come from the shared contract.

## Output structure

```
${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/
├── AGENTS.md
├── log.md
├── <Agent>/                     one per item in AGENT_DIRS; runtime state, machine-managed
│   ├── config/                  the agent's own instruction and memory files
│   ├── ops/                     usage logs, snapshots, health series
│   ├── sessions/                per-run session files
│   └── skills/                  skill files the agent reads directly
├── Workstations/                (Fleet docs = Yes)
│   ├── Setup/                   workstation setup notes
│   ├── Skills/                  generated skills index
│   ├── Tools/                   per-tool reference
│   ├── References/              tool and memory reference notes
│   ├── Plans/                   plan notes for fleet engineering work
│   ├── Templates/               note templates
│   ├── Provisioning/            per-host tooling inventories
│   └── Bstack/                  agent-stack documentation
├── Sessions/                    flat session notes, YYYY-MM-DD <slug>.md
│   ├── Handoffs/                pickup prompts
│   └── Archive/
├── Audits/                      cross-agent synthesis at root
│   └── <Agent>/                 per-agent audits
├── Ops/                         skill evidence: journals, current-state reports, Ops/<name>/ corpora
└── Secrets/                     (Secrets = Yes)
```

## Workflow

Run the shared scaffolding contract in [`../SKILL.md`](../SKILL.md). This workflow supplies the type-specific pieces below.

- **Inputs**: the panel and text fields above. Parse `AGENT_DIRS` into an array.
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
- **Templates** (steps 4 + 6): `../templates/agents/AGENTS.md.tmpl` and `../templates/agents/log.md.tmpl`. Beyond the standard variable set the AGENTS.md template takes these strings, built in code first:
  - `{{TOP_LEVEL_FOLDERS_LIST}}` - one bullet per top-level folder created, bold name then its role in one sentence, in the order of the tree above
  - `{{AGENT_UNIVERSES}}` - one `### <Agent>` heading per agent folder with a four-row table (`config/`, `ops/`, `sessions/`, `skills/`) carrying a contents cell and a retention cell of `tbd - set policy`
  - `{{SECRETS_DIR_DESCRIPTION}}` - Yes: "`Secrets/` holds exactly one encrypted credentials file. Its password is injected at runtime on the host that reads it and stays separate from the vault." No: "Agents read credentials from the host's secrets store directly."
  - `{{SEARCH_INDEXED}}` - `true` or `false`; `{{SEARCH_INDEXED_DESCRIPTION}}` - "read by direct file access" or "search-indexed; collection `<name>`"
  - `{{ECOSYSTEM_NAME}}` and `{{INCLUDE_WORKSTATIONS_DIR}}` from the inputs above
  - log.md takes `{{AGENT_DIRS_LIST}}`, `{{INCLUDE_WORKSTATIONS_DIR}}` and `{{SECRETS_DIR_ENABLED}}`
- **Verify** (step 8): `vault_type: agents`. Also confirm `Ops/`, `Sessions/Handoffs/`, `Audits/<agent>/` and each agent folder exist.

### Type-specific notes

- **Search registration is usually off.** Agents read these files by direct access. Register only where the Intake panel said Now; the collection name is the lowercased `VAULT_NAME`.
- **Sync toggles.** An agents vault usually holds non-Markdown state - JSON snapshots, chart images, an encrypted credentials file - so the Intake Files answer is Mixed in practice and step 9 of the shared contract applies on every device.
- **The final report** (step 10) restates the cross-vault boundary rule, and reminds the user to point every scheduled writer at the new per-agent paths and to give each output folder a retention row before its job goes live.
- This workflow creates the vault scaffold. Agent configuration, server runtime stores, credential-manager setup and scheduled-job mirrors are separate work.

## Template files (self-contained)

| File | Path | Role |
|---|---|---|
| AGENTS.md template | `../templates/agents/AGENTS.md.tmpl` | Full agents-vault contract: vault-root rule, where-things-go table, agent folders, flat sessions with the closed `status:` vocabulary, audits, `Ops/`, secrets, retention, the boundary rule, maintenance entrypoints |
| log.md template | `../templates/agents/log.md.tmpl` | Initial runtime-log entry recording the scaffold |
