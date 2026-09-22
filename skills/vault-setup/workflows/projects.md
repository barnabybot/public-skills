# Projects vault - scaffold workflow

Creates a new projects-type vault at `${VAULTS_ROOT:-$HOME/vaults}/<NAME>/`,
organised on a **three-phase lifecycle**: Planning, Delivery, Reporting.
Delivery is the heavy working folder where most knowledge work lives (Meetings,
Correspondence, Analysis). Reporting holds outputs and close-out artefacts.

The scaffold pre-populates entity stubs and deliverable shells, so the vault
does not accumulate broken-wikilink debt over the project's lifetime.

Every template lives in `../templates/projects/` inside the skill folder.

## Shape

- **Three phase folders** at top level: `Planning/`, `Delivery/`, `Reporting/`.
  Each carries a phase hub note with an artefact-status table that doubles as
  the progress indicator.
- **Delivery is the heavy folder** - `Analysis/<Axis>/<Item>/`, `Meetings/`,
  `Correspondence/`, `Working Files/`.
- **Reporting holds outputs and close-out** - `Draft Report.md`, `Findings
  Log.md`, `Key Findings Overview.md`, `Review Notes.md`, `Final Report.md`,
  `Debrief.md`, `Lessons Learned.md`.
- **Progress signal is the artefact-status table** in each phase hub, plus the
  phase-RAG row on the Dashboard. Explicit exit-criteria checklists were
  considered and dropped: a project lead already knows when a phase is done, and
  the table of artefacts carries the same signal with less ceremony.

## Inputs

Gather these with one question panel per batch, and never one question per turn.

### Required (first batch)

| Variable | Type | Example |
|----------|------|---------|
| `VAULT_NAME` | required | `Phoenix` |
| `PROJECT_CONTEXT` | required, one paragraph | Who it is for, what it is, the scope, the headline thesis |
| `PROJECT_TYPE` | required | `Assessment` \| `Implementation` \| `Review` \| `Research` \| `Other` |
| `PROJECT_LEAD` | required | The person accountable for delivery |
| `START_DATE` | required | YYYY-MM-DD, defaults to today |
| `TARGET_COMPLETION` | required | YYYY-MM-DD, defaults to today plus twelve weeks |
| `STRUCTURE_AXIS` | required choice | `Workstreams` \| `Modules` \| `Business Lines` |
| `STRUCTURE_VALUES` | required list | `Module 1 - Discovery, Module 2 - Build, Module 3 - Rollout` |
| `SEARCH_COLLECTION` | required | lowercase, defaults to the lowercased `VAULT_NAME` |

### Optional (second batch, skipped where not applicable)

| Variable | Type | Example |
|----------|------|---------|
| `SPONSOR_NAME` | optional | the organisation or person the work is for |
| `COUNTERPARTY_NAME` | optional | a second party, where the project has one |
| `CODE_NAMES` | optional list of pairs | `Ruby = North region, Sapphire = South region` |
| `EXTERNAL_PARTIES` | optional list | other firms or teams involved |
| `NAMED_DELIVERABLES` | optional list | `Final Report, Findings Pack` |
| `KEY_ABBREVIATIONS` | optional list of pairs | `TCO = Total Cost of Ownership` |
| `PROJECT_TEAM` | optional list of name/role pairs | `A. Name = Project Lead, ...` |
| `REGISTER_SEARCH` | required choice | `yes` \| `no` |

Set `CREATED` to today's date.

## Output structure

```
${VAULTS_ROOT:-$HOME/vaults}/<VAULT_NAME>/
├── AGENTS.md
├── log.md
│
├── 00 Start.md                        Vault entry point
├── 00 To Do.md                        Kanban
├── 01 Dashboard.md                    Phase RAG, workstream RAG, deliverable status
├── 02 Action Tracker.md
├── 03 Decision Log.md
├── 04 Issues & Risks Log.md
├── Project <VAULT_NAME>.md            Identity hub: one-paragraph thesis plus links
│
├── Planning/
│   ├── Planning.md                    Phase hub
│   ├── Scope of Work.md               THE anchor, built from inputs
│   ├── Team RACI.md                   Stub, seeded from PROJECT_TEAM
│   ├── Session Schedule.md            Stub
│   ├── Execution Plan.md              Stub
│   ├── Open Questions.md              What must be answered, and by whom
│   └── Assumptions Log.md             What the work rests on, and whether it is tested
│
├── Delivery/
│   ├── Delivery.md                    Phase hub
│   ├── Analysis/
│   │   └── <STRUCTURE_AXIS>/          e.g. Workstreams/, Modules/
│   │       └── <value 1>/
│   │           └── <value 1>.md       Hub stub
│   ├── Meetings/                      Empty - YYYY-MM-DD Title.md
│   ├── Correspondence/                Empty
│   └── Working Files/                 Empty - spreadsheets, extracts, exports
│
├── Reporting/
│   ├── Reporting.md                   Phase hub
│   ├── Draft Report.md                Skeleton with sections
│   ├── Key Findings Overview.md
│   ├── Findings Log.md
│   ├── Review Notes.md
│   ├── Final Report.md                Empty - copied from Draft Report at sign-off
│   ├── Debrief.md
│   └── Lessons Learned.md
│
├── People/                            Team stubs, where names were given
├── Entities/                          Empty - populated as organisation profiles emerge
├── Concepts/                          Code-name and abbreviation stubs
├── References/                        Sponsor, counterparty and external-party stubs
├── Deliverables/                      One shell per NAMED_DELIVERABLES item
├── Attachments/                       Empty
├── Templates/                         Empty
└── Archive/                           Empty
```

## Workflow

Run the shared scaffolding contract in [`../SKILL.md`](../SKILL.md). This
workflow supplies the type-specific pieces below. A project is
information-dense, so input gathering runs in two batches and the scaffold
pre-populates entity stubs and deliverable shells.

- **Inputs**: the two tables above, in two batches. Parse comma-separated lists
  into arrays, and pair lists (`X = Y, A = B`) into ordered dictionaries. At
  confirmation, print the stub list - every entity, code-name, deliverable and
  abbreviation that will be created - and the structure-axis subfolders
  enumerated under `Delivery/Analysis/`.

- **Folder tree** (step 3):

  ```bash
  VAULT="${VAULTS_ROOT:-$HOME/vaults}/$VAULT_NAME"
  mkdir -p "$VAULT"/{Planning,"Delivery/Meetings","Delivery/Correspondence","Delivery/Working Files",Reporting,People,Entities,Concepts,References,Deliverables,Attachments,Templates,Archive}
  # zsh does not word-split an unquoted variable, so read the list rather than
  # looping over it - a for-loop here runs once, over the whole string.
  echo "$STRUCTURE_VALUES" | tr ',' '\n' | while IFS= read -r v; do
    v="$(echo "$v" | sed 's/^ *//;s/ *$//')"
    [ -n "$v" ] && mkdir -p "$VAULT/Delivery/Analysis/$STRUCTURE_AXIS/$v"
  done
  ```

- **Templates** (steps 4 and 6): every `../templates/projects/*.tmpl` file in
  the table below. The AGENTS.md and phase-hub templates need dynamic table
  strings built in code first, per the list below. Verify (step 8):

  ```bash
  grep -q '^vault_type: projects' "$VAULT/AGENTS.md" && echo "vault_type declared"
  test -f "$VAULT/Planning/Planning.md"   && echo "Planning hub present"
  test -f "$VAULT/Delivery/Delivery.md"   && echo "Delivery hub present"
  test -f "$VAULT/Reporting/Reporting.md" && echo "Reporting hub present"
  test -d "$VAULT/Delivery/Analysis/$STRUCTURE_AXIS" && echo "Analysis axis subfolders present"
  # No unsubstituted template tokens survived the write:
  grep -rl '{{' "$VAULT" && echo "WARNING: unsubstituted tokens above" || echo "no unsubstituted tokens"
  ```

### Type-specific write pass

After the generic AGENTS.md write, this scaffold also writes the cockpit docs,
the phase hubs, the anchor artefacts and the pre-populated stubs.

**Build the dynamic table strings** for AGENTS.md and phase-hub substitution
before writing:

- `{{STRUCTURE_VALUES_LIST}}` - a Markdown list, one line per structure value
- `{{ABBREVIATIONS_TABLE}}` - a table from `KEY_ABBREVIATIONS` pairs (header: Abbreviation / Full name)
- `{{SPONSOR_STAKEHOLDERS_TABLE}}` - a placeholder row where `SPONSOR_NAME` is set, otherwise `(to be populated)`
- `{{COUNTERPARTY_STAKEHOLDERS_TABLE}}` - the same pattern
- `{{PROJECT_TEAM_TABLE}}` - team rows, where provided
- `{{EXTERNAL_PARTIES_LIST}}` - `[[Party]] - <role>` lines
- `{{STRUCTURE_RAG_ROWS}}` - one dashboard row per structure value
- `{{STRUCTURE_AXIS_SINGULAR}}` - the singular form (Workstream, Module)
- `{{STRUCTURE_AXIS_LOWERCASE}}` - the frontmatter key form (`workstream`, `module`)
- `{{NAMED_DELIVERABLES_LIST}}` - a bulleted list of the deliverable shells created
- `{{PROJECT_TEAM_LIST_PEOPLE}}` - names extracted from `PROJECT_TEAM`, for People stubs

`log.md` takes four more, each built after the stubs are written so the log
records what actually landed, plus a short context line:

- `{{PROJECT_CONTEXT_SHORT}}` - `PROJECT_CONTEXT` cut to one sentence
- `{{REFERENCE_STUB_LIST}}` - the reference stubs created, or `none`
- `{{CONCEPT_STUB_LIST}}` - the concept and abbreviation stubs created, or `none`
- `{{DELIVERABLE_STUB_LIST}}` - the deliverable shells created, or `none`
- `{{PEOPLE_STUB_LIST}}` - the People stubs created, or `none`

The three stub templates take their own: `concept-stub` and `reference-stub`
take `{{NAME}}`, `{{DESCRIPTION}}`, `{{BODY}}` and `{{NOTES}}`;
`deliverable-stub` takes `{{NAME}}`, `{{DESCRIPTION}}`, `{{DESCRIPTION_PARA}}`
and `{{PHASE}}`. Substitute every one, because the step-8 check fails on any
`{{` left in the tree.

**Write the cockpit docs** by reading and substituting:

- `../templates/projects/cockpit-00-start.md.tmpl` → `$VAULT/00 Start.md`
- `../templates/projects/cockpit-00-to-do.md.tmpl` → `$VAULT/00 To Do.md`
- `../templates/projects/cockpit-01-dashboard.md.tmpl` → `$VAULT/01 Dashboard.md`
- `../templates/projects/cockpit-02-action-tracker.md.tmpl` → `$VAULT/02 Action Tracker.md`
- `../templates/projects/cockpit-03-decision-log.md.tmpl` → `$VAULT/03 Decision Log.md`
- `../templates/projects/cockpit-04-issues-risks-log.md.tmpl` → `$VAULT/04 Issues & Risks Log.md`
- `../templates/projects/project-hub.md.tmpl` → `$VAULT/Project $VAULT_NAME.md`

**Write the three phase hubs**:

- `../templates/projects/phase-hub-planning.md.tmpl` → `$VAULT/Planning/Planning.md`
- `../templates/projects/phase-hub-delivery.md.tmpl` → `$VAULT/Delivery/Delivery.md`
- `../templates/projects/phase-hub-reporting.md.tmpl` → `$VAULT/Reporting/Reporting.md`

**Write the Planning anchor artefacts** as pre-populated stubs:

- `$VAULT/Planning/Scope of Work.md` - sections built from `PROJECT_CONTEXT`,
  `SPONSOR_NAME`, `STRUCTURE_VALUES`, `NAMED_DELIVERABLES`, `START_DATE`,
  `TARGET_COMPLETION` and `PROJECT_TEAM`
- `$VAULT/Planning/Team RACI.md` - seeded from `PROJECT_TEAM`
- `$VAULT/Planning/Session Schedule.md` - an empty table
- `$VAULT/Planning/Execution Plan.md` - a skeleton
- `$VAULT/Planning/Open Questions.md` - a register: question, owner, needed by, status
- `$VAULT/Planning/Assumptions Log.md` - a register: assumption, why it matters, tested yes or no, source

**Write the Reporting anchor artefacts**:

- `$VAULT/Reporting/Draft Report.md` - a skeleton with sections (Executive
  Summary, Key Findings, Workstream Sections, Appendices)
- `$VAULT/Reporting/Key Findings Overview.md` - an empty list with severity,
  workstream and status columns
- `$VAULT/Reporting/Findings Log.md` - a per-finding register
- `$VAULT/Reporting/Review Notes.md` - empty
- `$VAULT/Reporting/Final Report.md` - empty, populated at sign-off
- `$VAULT/Reporting/Debrief.md` - a facilitation guide plus empty notes
- `$VAULT/Reporting/Lessons Learned.md` - what to repeat, what to change

**Write the Analysis hub stubs** - one `<value>.md` per structure value, inside
its own subfolder under `Delivery/Analysis/<STRUCTURE_AXIS>/<value>/`. Each hub
note links back to the relevant phase hubs and cockpit docs.

**Write the pre-populated entity stubs**, which are the broken-wikilink guard:

- Entity stubs from `../templates/projects/reference-stub.md.tmpl` - one per
  `SPONSOR_NAME`, one per `COUNTERPARTY_NAME` where set, and one per
  `EXTERNAL_PARTIES` entry, into `$VAULT/References/`
- Code-name stubs from `../templates/projects/concept-stub.md.tmpl` per
  `CODE_NAMES` pair: `Ruby = North region` → `$VAULT/Concepts/Ruby.md`
- Abbreviation stubs from the same template per `KEY_ABBREVIATIONS` pair
- Team stubs per `PROJECT_TEAM` name - a minimal People stub with `type:
  "[[People]]"` and the role from the pair, into `$VAULT/People/`
- Deliverable shells from `../templates/projects/deliverable-stub.md.tmpl` per
  `NAMED_DELIVERABLES` entry, substituting `{{NAME}}` and `{{DESCRIPTION}}`,
  with `phase: reporting` by default, into `$VAULT/Deliverables/`

The final report adds file counts per phase folder, cross-phase folder counts,
and the project's next steps.

## Type-specific notes

- The scaffold structures the project. The project's strategy and scope come
  from the people doing it, and not from this skill.
- The phase names are a default. A project that runs discovery, build and
  rollout should say so - rename the three folders and the three hub notes
  together, and update the Dashboard's phase-RAG rows to match.

## Template files

| File | Path | Role |
|------|------|------|
| AGENTS.md template | `../templates/projects/AGENTS.md.tmpl` | The full projects-vault contract, with placeholders |
| 00 Start | `../templates/projects/cockpit-00-start.md.tmpl` | Vault entry point, one screen of orientation |
| 00 To Do | `../templates/projects/cockpit-00-to-do.md.tmpl` | Kanban board |
| 01 Dashboard | `../templates/projects/cockpit-01-dashboard.md.tmpl` | Phase RAG, workstream RAG, deliverable status |
| 02 Action Tracker | `../templates/projects/cockpit-02-action-tracker.md.tmpl` | Action table |
| 03 Decision Log | `../templates/projects/cockpit-03-decision-log.md.tmpl` | Decision table |
| 04 Issues & Risks Log | `../templates/projects/cockpit-04-issues-risks-log.md.tmpl` | Risk register |
| Project hub | `../templates/projects/project-hub.md.tmpl` | `Project <Name>.md`, the identity hub |
| Planning hub | `../templates/projects/phase-hub-planning.md.tmpl` | `Planning/Planning.md` |
| Delivery hub | `../templates/projects/phase-hub-delivery.md.tmpl` | `Delivery/Delivery.md` |
| Reporting hub | `../templates/projects/phase-hub-reporting.md.tmpl` | `Reporting/Reporting.md` |
| Concept stub | `../templates/projects/concept-stub.md.tmpl` | For code-names and abbreviations |
| Reference stub | `../templates/projects/reference-stub.md.tmpl` | For sponsor, counterparty and external-party entities |
| Deliverable shell | `../templates/projects/deliverable-stub.md.tmpl` | For named deliverables in the scope |
| log.md | `../templates/projects/log.md.tmpl` | The runtime-log entry recording the scaffold |

All template variables use `{{VARIABLE_NAME}}` and are substituted at scaffold
time. Tables and lists with dynamic row counts are built in code before
substitution.
