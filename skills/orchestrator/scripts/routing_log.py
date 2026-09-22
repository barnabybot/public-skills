"""Local evidence for orchestrator routing checks."""
import os
from datetime import datetime, timezone
from pathlib import Path


def vault_root():
    return Path(os.environ.get("ORCHESTRATOR_VAULT_ROOT", Path.home() / "Obsidian")).expanduser()


def append_evidence(command, status, summary):
    path = vault_root() / "Agents/Ops/orchestrator/routing-log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(f"- {datetime.now(timezone.utc).isoformat()}: {command} {status}: {summary}\n")
