# AGENTS.md

Root agent instructions map the collection's files and verification commands.
They link `home/global.md` for the shared steering rules.

## Sub-features

- `agents-present`. Both collection instruction files are non-empty.

## How to get to it (user POV)

Read root `AGENTS.md` when locating the repository's skills and checks. Use
its child-project starter to write instructions for another destination.
The global symlink setup is described separately in that file.

Source: [AGENTS.md](../../../../AGENTS.md), especially Verification gates and
Child project or vault starter, and [global steering](../../../../home/global.md).

## Live recipe

Use [Launch and Doctor](../SKILL.md) in a fresh CLI session, then run:

```bash
test -s AGENTS.md
test -s home/global.md
wc -c AGENTS.md home/global.md
```

Keep the byte counts and process exit 0.

## Gotchas

- Presence checks establish readable, non-empty files. Content review and
  enforcement of the rules need separate evidence.
