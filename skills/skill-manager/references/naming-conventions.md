# Naming conventions

## Folder and name: field

- Folder name = frontmatter `name:` (lowercase, hyphens, ≤64 chars).
- **Exception — cross-stack invocation names.** When a child skill is called
  from outside its parent stack, `name:` may use the shorter slash-command form
  (e.g. folder `writing-editorial-review/` with `name: editorial-review` so
  callers invoke `/editorial-review`). The folder still carries the stack prefix
  for directory discovery.

## Families: native vs adopted children

A family is a folder of related skills with one router skill at its root, e.g.
`research/` holding `research-screen/` and `research-memo/`.

- **Native children** always use `<family>-<child>/` naming (e.g.
  `research-screen/`, `notes-capture/`).
- **Adopted children** keep their original name when the skill has vendor
  provenance or its own identity. They declare `parent:` in frontmatter to
  establish the relationship. Example: `trip-planner/` lives under `life/` with
  `parent: life` but keeps its own name, because renaming would break the slash
  command people already type. A vendored skill also carries `forked_from:` and
  `pinned_at:` stamps.

## Other conventions

- Scripts: `verb-noun.py` (Python by default).
- Workflows: `workflow-name.md`, or `workflow-name.js` for a dynamic workflow.
- Utility folders (references/, scripts/, templates/, fonts/) do not carry the
  family prefix.

## Renaming an existing skill folder

A rename is not done when the folder moves — stale references break silently:

- `grep -rn '<old-name>'` across sibling scripts, configs, workflows, and
  headless runners. A missed path does not error. It disables the dependent: in
  one rename, a stale path left a scoring script unrun, so a model silently
  dropped from seven inputs to five and inflated the rest.
- Sub-scripts that resolve output dirs against their own root need an
  **absolute** path passed in — a relative dir writes outside the intended tree.
- Update the symlinks (`discovery-workflow.md`) and any cron or scheduler
  entries that name the old path.
