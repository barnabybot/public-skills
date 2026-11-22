# Agent Safety and Blast-Radius Audit Workflow

Follow the prompt below verbatim during Pillar 5 of `/hygiene` (or when running
a focused `safety` pass).

## Prompt (Verbatim)

Audit this repo and my dev setup for the issues I list below.
Rules: audit first and change nothing. Never print secret values or use any credential; show names and paths only. Report each finding with file:line, why it's dangerous, and the fix below. Then wait for my approval. Apply only in-repo fixes. List anything outside the repo (accounts, tokens, settings) as manual steps for me.

1. Check: test/dev/preview configs (.env*, test setup, docker-compose, DB config) pointing at a non-local or production DB, especially if tests drop, truncate, reset or migrate it.

Fix: point tests at a local or container DB, and add a guard in test setup that aborts if the DB host isn't local.

2. Check: production or broad-scope credentials my shell can read (env var names, ~/.aws, ~/.kube, ~/.config/gcloud, ~/.netrc, ~/.pgpass, gh/npm/cloud CLI tokens, keys in the repo, live payment keys). Is the default context production?

Fix: remove committed keys and add them to .gitignore. Manual: rotate any exposed key, move prod creds to an account this user can't read, make non-prod the default context.

3. Check: recursive deletes whose target comes from a variable, glob or link (rm -rf "$VAR", rmtree, rimraf), scripts without set -u, symlinks/junctions in folders that get cleaned, tests that change HOME.

Fix: use ${VAR:?} guards and set -euo pipefail, resolve with realpath and refuse targets outside the repo root, and add a dry-run that prints the target and file count.

4. Check: infrastructure one command can destroy: DBs without deletion_protection/prevent_destroy, stray *.tfstate files, auto-approve/--force flags, backups the same token can delete.

Fix: add deletion_protection/prevent_destroy to data resources and drop auto-approve from scripts. Manual: delete or archive stray state files, and store backups where the agent's token can't delete them.

5. Check: rules that exist only as prose (AGENTS.md, CLAUDE.md, .cursorrules: "code freeze", "never", "ask before"). What enforces each one outside the model?

Fix: back each rule with a real control (deny rule in agent settings, read-only DB role, branch protection, required review), and name the safe command next to the rule (e.g. "run tests with make test-local").

6. Check: is main protected? What scopes does my gh token have? Can it force-push, delete repos, or create public repos?

Fix (manual): protect main with required reviews and no force-push, use a fine-grained token scoped to this repo, and block public repo creation in the org.

7. Check: is this folder inside iCloud, Dropbox or OneDrive, and are there zero-byte or cloud-only placeholder files?

Fix: move the repo out of synced folders (manual). In scripts, verify copy size and content before deleting a source, and prefer mv to copy-then-delete.

8. Check: list every MCP config and flag unpinned servers (@latest, npx -y), hooks (SessionStart etc.), install scripts, skills, permission-bypass flags (--dangerously-skip-permissions, --yolo) and hidden Unicode in rule files.

Fix: pin server versions, remove unknown hooks, servers and skills, strip hidden Unicode, and give MCP servers read-only tokens where they only read.

9. Check: CI workflows that run an AI agent on untrusted input (issues, PR comments, pull_request_target) while it can see secrets or write access.

Fix: set least-privilege permissions, keep secrets out of agent jobs, avoid pull_request_target for agents, and don't share caches with release jobs.

10. Check: auto-approve or full-access agent modes, and safety nets agents don't load (e.g. an rm alias in .zshrc; test with bash -c 'type rm').

Fix (manual): turn off bypass/auto-approve for destructive commands, sandbox the agent to the project dir, and put guards in scripts or agent deny rules instead of shell aliases.

11. Check: tools that send money or messages without a cap, allowlist or confirmation.

Fix: add a per-call cap, a recipient allowlist, explicit units on amounts, and human confirmation.

Finally: for any risky command that must stay, add a warning in its output that names the hazard and its consequence (e.g. "WARNING: DATABASE_URL is production; this DROPS tables"). The study found that kind of warning cut agent harm far more than restating a rule. Rank all fixes by blast radius, top 3 first.
