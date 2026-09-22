# Operations vault - scaffold workflow

Creates a new operations-type vault at `${VAULTS_ROOT:-$HOME/vaults}/<NAME>/`. Operations vaults hold how a practice or team runs: reusable methods, propositions, meeting records, internal delivery and team operations.

All templates and conventions live in `../templates/operations/` inside the skill folder.

## Inputs (gathered via AskUserQuestion)

| Variable | Type | Example |
|----------|------|---------|
| `VAULT_NAME` | required | `Tax` |
| `PRACTICE_AREA` | required | `Tax Advisory` |
| `OWNER` | required | Your full name |
| `ROLE` | required | `Head of Tax Advisory` |
| `FIRM` | required | e.g. `Acme Consulting` |
| `COVERAGE` | required | e.g., "Transfer pricing, M&A tax, indirect tax, tax controversy" |
| `SERVICE_LINES` | required list | e.g., `Transfer Pricing, M&A Tax, Indirect Tax` |
| `SEARCH_COLLECTION` | required | `tax` (lowercase) |
| `REGISTER_SEARCH` | required choice | `yes` \| `no` |

Set `CREATED` to today's date.

For `SERVICE_LINES`: gather as a comma-separated list. Each becomes a subfolder under `Methodologies/`.

## Output structure

```
${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/
├── AGENTS.md                Operations-vault contract
├── log.md                   Operational log (from templates/log.md.tmpl)
├── Methodologies/
│   ├── <Service Line 1>/    one subfolder per item in SERVICE_LINES
│   ├── <Service Line 2>/
│   └── ...
├── Go to Market/
│   ├── Propositions/
│   ├── Proposals/
│   ├── Thought Leadership/
│   └── Events/
├── Operations/
├── Technology/
│   ├── Skills/
│   ├── Workflows/
│   └── Strategy/
├── Mental Models/
├── Projects/
├── People/
├── Clippings/
│   ├── Articles/
│   ├── Books/
│   ├── PDFs/
│   ├── Podcasts/
│   ├── Tweets/
│   └── Youtube/
├── References/
├── Templates/
├── Inbox/
│   └── Staging/
├── Attachments/
└── Archive/
```

## Workflow

Run the shared scaffolding contract (see [`../SKILL.md`](../SKILL.md)) — gather inputs, confirm, create tree, write AGENTS.md, reverse-symlink, write log, register QMD, verify, report. This skill supplies the type-specific pieces:

- **Inputs**: the table above. For `SERVICE_LINES`, parse the comma-separated list into an array — each becomes a subfolder under `Methodologies/`.
- **Folder tree** (step 3):
  ```bash
  VAULT="${VAULTS_ROOT:-$HOME/vaults}/$VAULT_NAME"
  mkdir -p "$VAULT"/{"Go to Market"/{Propositions,Proposals,"Thought Leadership",Events},Operations,Technology/{Skills,Workflows,Strategy},"Mental Models",Projects,People,Clippings/{Articles,Books,PDFs,Podcasts,Tweets,Youtube},References,Templates,Inbox/Staging,Attachments,Archive}
  # Methodologies subfolders per service line
  # zsh does not word-split an unquoted variable, so read the list rather than
  # looping over it - a for-loop here runs once, over the whole string, and a
  # multi-word service line silently becomes one folder per word.
  echo "$SERVICE_LINES" | tr ',' '\n' | while IFS= read -r sl; do
    sl="$(echo "$sl" | sed 's/^ *//;s/ *$//')"
    [ -n "$sl" ] && mkdir -p "$VAULT/Methodologies/$sl"
  done
  ```
- **Templates** (steps 4 + 6): `../templates/operations/AGENTS.md.tmpl` and `../templates/operations/log.md.tmpl` below. Before writing AGENTS.md, build the methodology-subfolders table for the `{{METHODOLOGY_SUBFOLDERS}}` placeholder (this is the one type-specific substitution beyond the standard variable set). For each service line in `SERVICE_LINES`, generate a row:
  ```
  | `Methodologies/<service-line>/` | <service line> methodology — frameworks, playbooks, training materials |
  ```
  Concatenate with a header row:
  ```
  | Subfolder | Service Line |
  |-----------|--------------|
  ```
  log.md additionally takes `{{SERVICE_LINES_LIST}}` (the comma-separated list).
- **Verify grep** (step 8): `vault_type: operations`. Also confirm the per-service-line subfolders exist: `ls "$VAULT/Methodologies"`.

Operations-specific note: leave `Mental Models/` empty at scaffold time. Those notes accumulate as the team's reusable thinking matures, and forcing them early produces stubs nobody reads.

## Template files (self-contained)

| File | Path | Role |
|------|------|------|
| AGENTS.md template | `../templates/operations/AGENTS.md.tmpl` | Operations-vault contract — boundary test, Kepano wikilink conventions, folder structure with per-service-line subfolders, property standards, ingestion workflow |
| log.md template | `../templates/operations/log.md.tmpl` | Initial operational-log entry recording the scaffold |

Variables in templates use `{{VARIABLE_NAME}}`. The `{{METHODOLOGY_SUBFOLDERS}}` variable is constructed at scaffold time from the `SERVICE_LINES` input.
