# Wiki vault — scaffold workflow

Creates a new wiki-type vault modelled on Andrej Karpathy's LLM-maintained-wiki pattern. A wiki vault differs from the other four types because the wiki pages themselves are LLM-maintained: knowledge compounds as new sources arrive, rather than being re-derived on every query. A wiki usually sits beside the skill that reads it, so that skill ships with its own corpus, and that is the default location.

Pattern attribution: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

This skill is fully self-contained — every template lives in `../templates/wiki/`.

## Inputs

Choices, one panel after the Intake panel:

**Location** — Where does the wiki live?
- Beside its skill — `<skills-dir>/<skill>/wiki/`, so the reading skill ships with its own corpus. A symlink at `${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>` keeps your editor and any vault-walking tool finding it (Recommended)
- Standalone — `${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>/`, for a wiki no skill reads
- settled by: a named skill or family in the request (Beside its skill)

**Ingest** — How do sources arrive?
- Manual — one source at a time, on demand (Recommended)
- Batch — `raw/_inbox/` fills up and a scheduled run ingests the queue
- settled by: "cron" or "scheduled" (Batch)

**Lint** — How often does the schema lint run?
- Weekly — run the `schema.md` lint criteria on a weekly cadence (Recommended)
- Manual — lint when asked

The two answers become `{{INGEST_CADENCE}}` and `{{LINT_CADENCE}}` in the
templates.
- Off — no scheduled lint; `wiki-schema-check.py` runs on demand
- settled by: "no lint" (Off)

Text fields, one message: `WIKI_NAME`; `SKILL_DIR` when Location is Beside its skill; `DOMAIN` (one sentence naming the body of work the wiki covers); `DOMAIN_DESCRIPTION` (one or two paragraphs); `ADDITIONAL_WIKI_FOLDERS` (optional list of extra wiki-layer folders, e.g. `Models` for a mental-model latticework); `SEED_CONCEPTS` and `SEED_PEOPLE` (optional lists of stub pages). `SEARCH_COLLECTION` defaults to the lowercased `WIKI_NAME`; `REGISTER_SEARCH` comes from the Intake panel. Set `CREATED` to today's date.

A wiki beside its skill is carried in every clone of that skill's repository, so treat it as published to everyone who has the repository. Confidential material belongs in a projects vault instead.

## Output structure

```
<SKILL_DIR>/wiki/                (Beside its skill; symlinked as ${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>)
${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>/          (Standalone)
├── AGENTS.md                    vault contract (three-layer table, ops instructions, mode entrypoints)
├── schema.md                    page taxonomy, per-type schemas, ingestion rules, lint criteria
├── index.md                     wiki-page catalog (LLM-maintained)
├── log.md                       append-only operational log
├── raw/                         Karpathy layer 1 — source documents, immutable
│   ├── _inbox/                  new material awaiting ingest
│   ├── Articles/                web clippings, transcripts, blog posts
│   ├── Books/                   one subfolder per book: chapter markdowns + PDF/symlink + INDEX.md
│   └── images/                  figures extracted from raw sources
├── Concepts/                    wiki — one page per recurring concept
├── People/                      wiki — one page per person referenced in the corpus
├── Books/                       wiki — one summary page per book (peer-level with each other)
├── 00-Hubs/                     wiki — map-of-content pages grouping Concepts
└── Routes/                      wiki — practical audit checklists (optional, domain-dependent)
```

Additional wiki-layer folders can be declared at scaffold time via `ADDITIONAL_WIKI_FOLDERS` (for example `Models/`, for a wiki that compiles a set of mental models). These land at the same level as `Concepts/`, `People/`, `Books/`, `00-Hubs/`, `Routes/`.

## Workflow

Run the shared scaffolding contract (see [`../SKILL.md`](../SKILL.md)) — gather inputs, confirm, create tree, write AGENTS.md, reverse-symlink, write log, register QMD, verify, report. The wiki type carries more moving parts than the other scaffolds (a five-file template set, dynamic extra-folder strings, and optional seed pages), so the type-specific pieces below extend the generic steps:

- **Inputs**: the panel and text fields above. Parse comma-separated lists into arrays.
- **Folder tree** (step 3):
  ```bash
  case "$LOCATION" in
    beside)     VAULT="$SKILL_DIR/wiki" ;;
    standalone) VAULT="${VAULTS_ROOT:-$HOME/vaults}/$WIKI_NAME" ;;
  esac
  mkdir -p "$VAULT"/raw/{_inbox,Articles,Books,images}
  mkdir -p "$VAULT"/{Concepts,People,Books,"00-Hubs",Routes}
  # Optional extra wiki-layer folders
  # zsh does not word-split an unquoted variable, so read the list rather than
  # looping over it - a for-loop here runs once, over the whole string.
  echo "$ADDITIONAL_WIKI_FOLDERS" | tr ',' '\n' | while IFS= read -r f; do
    f="$(echo "$f" | sed 's/^ *//;s/ *$//')"
    [ -z "$f" ] && continue
    [ -n "$f" ] && mkdir -p "$VAULT/$f"
  done
  # Beside its skill: expose the wiki to your editor and any vault-walking tool,
  # all of which walk ${VAULTS_ROOT:-$HOME/vaults}/*/AGENTS.md
  [ "$LOCATION" = beside ] && mkdir -p "${VAULTS_ROOT:-$HOME/vaults}" && ln -s "$VAULT" "${VAULTS_ROOT:-$HOME/vaults}/$WIKI_NAME"
  ```
- **Dynamic template strings** (build these before the template-writing step — they handle any `ADDITIONAL_WIKI_FOLDERS`):
  - `{{ADDITIONAL_WIKI_FOLDERS_LIST}}` — comma-separated list of extra wiki folders (empty if none)
  - `{{ADDITIONAL_WIKI_FOLDERS_ROW}}` — append `, \`<Folder>/\`` per folder to the wiki-layer row in the three-layer table (AGENTS.md.tmpl); empty if none
  - `{{ADDITIONAL_WIKI_FOLDERS_TABLE}}` — one `| \`<Folder>/\` | <role> |` row per folder in the Wiki layer table (AGENTS.md.tmpl); empty if none
  - `{{ADDITIONAL_PAGE_TAXONOMY_ROWS}}` — one `| **<folder-name>** | \`<Folder>/\` | <role> |` row per folder in the page taxonomy table (schema.md.tmpl); empty if none
  - `{{ADDITIONAL_WIKI_FOLDERS_INLINE}}` — comma-separated backtick folder names for inline prose (index.md.tmpl); empty if none
  - `{{ADDITIONAL_WIKI_FOLDERS_INDEX_SECTIONS}}` — one `## <Folder>` section per folder for the index (index.md.tmpl); empty if none
  - `{{ADDITIONAL_WIKI_FOLDERS_LOG}}` — comma-separated list prefixed with `, ` for the log entry (log.md.tmpl); empty if none
  - `{{SEED_CONCEPTS_COUNT}}` / `{{SEED_PEOPLE_COUNT}}` — integer counts of the seed lists
  - `{{LOCATION_NOTE}}` — Beside its skill: "This wiki lives inside its skill at `<SKILL_DIR>/wiki/` and is symlinked in as `${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>` so vault-walking tools find it." Standalone: "This wiki lives at `${VAULTS_ROOT:-$HOME/vaults}/<WIKI_NAME>/`."
  - `{{LOCATION}}` — `beside its skill at <SKILL_DIR>/wiki` or `standalone` (log.md.tmpl)
- **Templates** (step 4 — wiki writes a five-file set, not just AGENTS.md + log):
  - `../templates/wiki/AGENTS.md.tmpl` → `$VAULT/AGENTS.md` — substitute `{{WIKI_NAME}}`, `{{DOMAIN}}`, `{{DOMAIN_DESCRIPTION}}`, `{{LOCATION_NOTE}}`, `{{SEARCH_COLLECTION}}`, `{{CREATED}}`, `{{ADDITIONAL_WIKI_FOLDERS_LIST}}` (plus the row/table strings above)
  - `../templates/wiki/schema.md.tmpl` → `$VAULT/schema.md` — substitute `{{WIKI_NAME}}`, `{{SEARCH_COLLECTION}}`, `{{CREATED}}`, `{{ADDITIONAL_WIKI_FOLDERS_LIST}}`, `{{ADDITIONAL_PAGE_TAXONOMY_ROWS}}`
  - `../templates/wiki/index.md.tmpl` → `$VAULT/index.md` — substitute `{{WIKI_NAME}}`, `{{CREATED}}`, `{{SEARCH_COLLECTION}}`, `{{ADDITIONAL_WIKI_FOLDERS_LIST}}` (plus the inline/section strings above)
  - `../templates/wiki/log.md.tmpl` → `$VAULT/log.md` — full log variable set
  - `../templates/wiki/seed-wiki-page.md.tmpl` → one page per `SEED_CONCEPTS` entry (concept variant) into `Concepts/`, and one per `SEED_PEOPLE` entry (person variant) into `People/`, substituting `{{PAGE_TITLE}}`, `{{CREATED}}`
- **Verify grep** (step 8): `vault_type: wiki`. Also confirm the wiki-specific tree: `schema.md`, `index.md`, `raw/_inbox`, `Concepts/`, `People/`, `Books/`, `00-Hubs/`, `Routes/`, `raw/Articles/`, `raw/images/`; for a wiki beside its skill, that the symlink resolves.
- **Report** (step 10): include the location and symlink, raw subfolders, wiki folders declared, seed pages created, and the wiki next step — drop first sources into `raw/_inbox/`, then run the first ingestion against it. A wiki beside its skill is committed with the skill, and the search collection is registered against that path.

Wiki-specific note: scaffolding stops at empty pages. Ingest, query and lint all run against the scaffolded vault afterwards. `raw/Books/<Book>/` subfolders land during the first ingest rather than at scaffold time. Migrating existing notes into wiki shape is a separate conversion task.

Ingest-time graph hygiene (see the `schema.md` ingestion rules and lint): raw source frontmatter (`people`/`author`/`topics` on chapters, INDEX, articles) must be **wikilinks, never plain strings** — Obsidian draws graph edges only from wikilinks, so plain-string values orphan the raw source; every raw book folder gets a `Books/<Book>.md` summary whose `## Source location` **wikilinks the raw stem** (this is what de-orphans it); the `INDEX.md` carries `type: book-index` + `categories: [[Books]]`. Page-granularity follows the Karpathy heuristic — a page for a distinct entity you'd link to, a section for an attribute of an existing concept (four lifecycle stages are sections of one concept, not four pages). Verbatim quotes are exempt from house-style normalisation.

## Template files (self-contained)

| File | Path | Role |
|------|------|------|
| AGENTS.md template | `../templates/wiki/AGENTS.md.tmpl` | Vault contract — the three-layer table, the raw layout, the wiki-layer table, the ingest / query / lint operations, and the property standards. |
| schema.md template | `../templates/wiki/schema.md.tmpl` | `schema_version: 4`. Page taxonomy table, per-page schemas (concept/book-summary/chapter/person/hub/route/article), ingestion rules, evidence roles, confidence tests, page status, index entry contract, log entry shape, lint criteria. |
| Seed wiki page | `../templates/wiki/seed-wiki-page.md.tmpl` | Three variants (concept, book summary, person) — schema-compliant frontmatter with placeholder sections |
| index.md template | `../templates/wiki/index.md.tmpl` | Books / Concept pages / People pages tables under the index entry contract (claim, source, use), Hubs / Routes / Raw layer / Retrieval order (scoped QMD query first). |
| log.md template | `../templates/wiki/log.md.tmpl` | Initial operational-log entry recording the scaffold |

## Pattern attribution

LLM-maintained wiki pattern from Andrej Karpathy: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f. The three-layer split (Sources / Wiki / Schema), the Ingest / Query / Lint operations, and the principle that "the tedious part of maintaining a knowledge base is the bookkeeping" come from there.
