# Personal vault — scaffold workflow

Creates a new personal-type vault at `${VAULTS_ROOT:-$HOME/vaults}/<NAME>/` that is fully self-contained — all templates and conventions ship inside this skill, no reads from existing vaults.

## Inputs (gathered via AskUserQuestion)

| Variable | Type | Example | Notes |
|----------|------|---------|-------|
| `VAULT_NAME` | required | `Writing` | becomes `${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/` |
| `VAULT_PURPOSE` | required | "Public-facing writing vault — drafts that may be published." | one-sentence; goes into AGENTS.md body |
| `SEARCH_COLLECTION` | required | `writing` | lowercase, defaults to lowercased `VAULT_NAME` |
| `ENABLE_DAILY_NOTES` | required choice | `yes` \| `no` | controls whether `Daily/` is created |
| `REGISTER_SEARCH` | required choice | `yes` \| `no` | run `qmd collection add` automatically |

Set `CREATED` to today's date in `YYYY-MM-DD` format.

## Output structure

```
${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/
├── AGENTS.md                Personal-vault contract (from templates/CLAUDE.md.tmpl)
├── log.md                   Operational log (from templates/log.md.tmpl)
├── Clippings/
│   ├── Articles/
│   ├── Tweets/
│   ├── Books/
│   ├── Podcasts/
│   ├── Youtube/
│   └── Voice Memos/
├── References/
│   └── People/
├── Daily/                   (only if ENABLE_DAILY_NOTES = yes)
├── Templates/               Empty
├── Projects/                Empty
└── Attachments/             Empty
```

## Workflow

Run the shared scaffolding contract (see [`../SKILL.md`](../SKILL.md)) — gather inputs, confirm, create tree, write AGENTS.md, reverse-symlink, write log, register QMD, verify, report. This skill supplies the three type-specific pieces:

- **Inputs**: the table above, plus `ENABLE_DAILY_NOTES` (yes/no — controls whether `Daily/` is created).
- **Folder tree** (step 3):
  ```bash
  VAULT="${VAULTS_ROOT:-$HOME/vaults}/$VAULT_NAME"
  mkdir -p "$VAULT"/{Clippings/{Articles,Tweets,Books,Podcasts,Youtube,"Voice Memos"},References/People,Templates,Projects,Attachments}
  if [ "$ENABLE_DAILY_NOTES" = "yes" ]; then mkdir -p "$VAULT/Daily"; fi
  ```
- **Templates** (steps 4 + 6): `../templates/personal/AGENTS.md.tmpl` and `../templates/personal/log.md.tmpl` below.
- **Verify grep** (step 8): `vault_type: personal`.

## Template files (self-contained)

| File | Path | Role |
|------|------|------|
| AGENTS.md template | `../templates/personal/AGENTS.md.tmpl` | Full personal-vault contract — Kepano method, property standards, filing decision tree, slash-command list, vault-log spec, inbox workflow, external-editing guidance |
| log.md template | `../templates/personal/log.md.tmpl` | Initial operational-log entry recording the scaffold |

Variables in templates are wrapped in double curly braces (`{{VARIABLE_NAME}}`). Substitution is a simple search-and-replace pass — no template engine required.
