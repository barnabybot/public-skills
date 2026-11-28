# Worker behaviour

Resolve every route and fallback through `../model-routing/scripts/preflight.py`.
Keep worker briefs short, pointer-based and verifiable.

- In T3 Code, follow delegate completion wakeups and `next`. Start a fresh `delegate_task` for every delegated review or re-check, and follow the T3 Code `delegate_task` boundary in `references/hosts.md` (force `isolation: "shared"` whenever `target.environmentId` names a linked environment).
- Pass file paths, issue URLs, branch names and verification commands rather than inlining long file contents or logs.
- Include this instruction in every dispatch brief: "Before reporting progress, audit each claim against a tool result from this session. Only report work you can point to evidence for; if something is not yet verified, say so explicitly."
- Include this instruction in every dispatch brief: "Remote branch hygiene (default): when your PR merges or closes, delete that remote branch. Also delete any dead worker remotes you created with no open PR. Never force-push. Never delete main or any still-open PR head."
- State the larger task, intended reader and purpose of the output.
- Bounded `delegate_task` children and workflow workers are exempt from the 30% / 300k context handoff ceiling and complete their single ticket. Only interactive coordinators and long-lived top-level threads hand off via `workflows/handoff.md`.
- Ask reviewers for every finding with confidence and severity, plus a coverage statement naming what was checked and what was excluded.
