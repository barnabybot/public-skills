# AGENTS.md

Root agent instructions shipped with the collection.

## Sub-features

- `agents-present` — `AGENTS.md` non-empty at repo root.

## How to get to it (user POV)

- Copy `AGENTS.md` to a project root and symlink `CLAUDE.md` to it.

## Driving it with preview-shots

- `test -s AGENTS.md`
- **Proof.** Exit 0.

## Gotchas

- Content judgement is human. Launch checks the file exists (`test -f`). This feature checks it is non-empty (`test -s`).
