"""Fault-tolerant batched Antigravity run_workflow script for Session Intelligence extraction.

Inlines digest text into flash-tier agent prompts with zero file or shell tool calls
inside workflow agents and persists each conv-<session_id>.json directly to <root>/data/runs/.

Args:
  scriptsDir (str, optional): absolute path to session-intelligence/scripts
  root (str): absolute path to the run directory
  count (int, optional): maximum missing sessions to process (default: all)
  label (str, optional): phase label
  model (str, optional): Antigravity model tier (default: "flash")
  concurrency (int, optional): parallel agents per wave (default: 24)
  kinds (list[str], optional): source_kinds to process (default: all)
  maxBatches (int, optional): maximum batches per run (default: 0 = all)
"""
import json
from pathlib import Path

root = Path(str(args["root"])).expanduser()
raw_count = args.get("count")
count = int(raw_count) if raw_count is not None else None
kinds_filter = set(args.get("kinds") or [])
max_batches = int(args.get("maxBatches") or 0)
concurrency = max(1, int(args.get("concurrency") or 24))
model_tier = str(args.get("model") or "flash")
label = str(args.get("label") or ",".join(sorted(kinds_filter)) or "all")

data_dir = root / "data"
runs_dir = data_dir / "runs"
runs_dir.mkdir(parents=True, exist_ok=True)

wl = {}
wl_path = data_dir / "work-list.jsonl"
if wl_path.is_file():
    for line in wl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            wl[row["session_id"]] = row

missing_path = data_dir / "missing-full.json"
missing_raw = json.loads(missing_path.read_text(encoding="utf-8")) if missing_path.is_file() else []
targets = []
for item in missing_raw:
    sid = item["session_id"]
    if (runs_dir / f"conv-{sid}.json").exists():
        continue
    meta = wl.get(sid)
    if not meta:
        continue
    if kinds_filter and meta.get("source_kind") not in kinds_filter:
        continue
    targets.append(meta)

targets.sort(key=lambda m: float(m.get("score") or 0), reverse=True)
if count is not None:
    targets = targets[: max(0, count)]

CONV_SCHEMA = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "title": {"type": "string"},
        "intent": {"type": "string"},
        "task_type": {
            "type": "string",
            "enum": [
                "content", "vault-eng", "outreach", "lead-gen", "video", "digest",
                "research", "coding", "admin", "automation", "analysis", "course", "other",
            ],
        },
        "skills_invoked": {"type": "array", "items": {"type": "string"}},
        "skills_missing": {"type": "array", "items": {"type": "string"}},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "friction": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "wrong-output", "redo", "clarification", "permission",
                            "tool-failure", "misunderstanding", "missing-context", "manual-steering",
                        ],
                    },
                    "what_went_wrong": {"type": "string"},
                    "cost": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["quote", "type", "what_went_wrong", "cost"],
            },
        },
        "toil": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "desc": {"type": "string"},
                    "evidence": {"type": "string"},
                    "frequency_hint": {"type": "string"},
                },
                "required": ["desc", "evidence", "frequency_hint"],
            },
        },
        "preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "rule": {"type": "string"},
                },
                "required": ["quote", "rule"],
            },
        },
        "outcome": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["completed", "partial", "abandoned", "unclear"]},
                "artifacts": {"type": "array", "items": {"type": "string"}},
                "committed": {"type": "boolean"},
                "summary": {"type": "string"},
            },
            "required": ["status", "artifacts", "committed", "summary"],
        },
        "automation_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["improve-skill", "new-skill", "new-cron", "agents-md-rule", "template-fix"],
                    },
                    "evidence": {"type": "string"},
                    "target": {"type": "string"},
                    "effort": {"type": "string", "enum": ["low", "medium", "high"]},
                    "payoff": {"type": "string", "enum": ["low", "medium", "high"]},
                    "rationale": {"type": "string"},
                },
                "required": ["title", "kind", "evidence", "target", "effort", "payoff", "rationale"],
            },
        },
    },
    "required": [
        "session_id", "title", "intent", "task_type", "skills_invoked", "skills_missing",
        "highlights", "friction", "toil", "preferences", "outcome", "automation_candidates",
    ],
}

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "sessions": {
            "type": "array",
            "items": CONV_SCHEMA,
        }
    },
    "required": ["sessions"],
}


def make_batches(items):
    batches = []
    cur = []
    cur_bytes = 0
    for meta in items:
        kind = meta.get("source_kind")
        dp = Path(meta.get("digest_path") or (data_dir / "digests" / f"{meta['session_id']}.txt"))
        text = dp.read_text(encoding="utf-8", errors="ignore") if dp.exists() else ""
        bsize = len(text.encode("utf-8"))
        if kind == "transcript":
            if cur:
                batches.append(cur)
                cur, cur_bytes = [], 0
            batches.append([(meta, text)])
            continue
        max_n = 11 if kind == "cron-failure" else 10
        max_b = 42000
        if cur and (len(cur) >= max_n or cur_bytes + bsize > max_b or cur[0][0].get("source_kind") != kind):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append((meta, text))
        cur_bytes += bsize
    if cur:
        batches.append(cur)
    return batches


INSTRUCTIONS_SINGLE = """Extract structured automation findings from this single agent session digest.

Each line in the digest is `[HH:MM] USER:` (the user's typed words or vault goal), `[HH:MM] AI:` (assistant first line or vault outcome), or `[HH:MM] .` (tool/skill call).
Ignore injected skill docs ("Base directory for this skill:"), harness preambles, and terminal banners.

HARD RULES:
- Copy `session_id` EXACTLY as given.
- Every `quote`, `evidence`, and `highlights` string MUST be verbatim substrings copied from THIS session's digest (keep exact typos, case-insensitive substring match is checked deterministically). Never fabricate or paraphrase quotes.
- `automation_candidates` must be concrete, specific, and grounded in a real verbatim quote from this digest. Empty arrays are fine when no real friction, toil, preference, or automation candidate exists.
- Return the structured object immediately via finish (no tool calls needed).
"""

INSTRUCTIONS_MULTI = """Extract structured automation findings for EVERY session digest below.

Return an object `{"sessions": [...]}` containing ONE entry per session in the exact order given, preserving each `session_id` verbatim.
Each line in a digest is `[HH:MM] USER:` (user words or `[Vault Goal]`), `[HH:MM] AI:` (assistant line or `[Vault Outcome]`), or `[HH:MM] .` (tool/skill call).

HARD RULES:
- Produce an entry for EVERY `session_id` in the bundle (do not skip any).
- Every `quote`, `evidence`, and `highlights` string MUST be verbatim substrings copied directly from THAT SAME session's digest (keep exact typos). Never fabricate or borrow quotes across sessions.
- For short routine `done` vault notes with no friction/toil/preference/automation signal, keep `title`, `intent`, `task_type`, `highlights` (1 verbatim quote from `[Vault Goal]` or body), and `outcome` concise, and use empty arrays `[]` for `friction`, `toil`, `preferences`, `automation_candidates`.
- For `blocked`, `failed`, or scheduled-job failure notes, capture the real friction and concrete `automation_candidates` with verbatim quotes.
- Return the structured object immediately via finish (no tool calls needed).
"""


def build_prompt(batch):
    if len(batch) == 1:
        meta, text = batch[0]
        return (
            f"{INSTRUCTIONS_SINGLE}\n"
            f"EXACT session_id: {meta['session_id']}\n"
            f"=== DIGEST START ===\n{text}\n=== DIGEST END ==="
        )
    parts = [INSTRUCTIONS_MULTI, f"Total sessions in this bundle: {len(batch)}"]
    for idx, (meta, text) in enumerate(batch, 1):
        parts.append(
            f"\n--- SESSION {idx}/{len(batch)} | EXACT session_id: {meta['session_id']} ---\n"
            f"{text}\n"
            f"--- END SESSION {idx}/{len(batch)} ---"
        )
    return "\n".join(parts)


if not targets:
    log("No missing sessions to extract.")
    print({"targeted": 0, "batches": 0, "written": 0, "failed_batches": 0})
else:
    batches = make_batches(targets)
    if max_batches > 0:
        batches = batches[:max_batches]

    stats = {"written": 0, "failed": 0}

    async def run_one_batch(batch_idx, batch):
        expected_ids = [m["session_id"] for m, _ in batch]
        expected_set = set(expected_ids)
        role = (
            f"Extract transcript {batch_idx + 1} ({expected_ids[0][:8]})"
            if len(batch) == 1
            else f"Extract {batch[0][0].get('source_kind')} batch {batch_idx + 1} ({len(batch)} sessions)"
        )
        prompt = build_prompt(batch)
        schema = CONV_SCHEMA if len(batch) == 1 else BATCH_SCHEMA
        try:
            res = await agent(prompt, schema=schema, role=role, model=model_tier)
        except Exception as exc:
            stats["failed"] += 1
            log(f"Batch {batch_idx + 1} FAILED ({role}): {exc}")
            return 0
        recs = [res] if len(batch) == 1 else (res.get("sessions") if isinstance(res, dict) else [])
        wrote = 0
        for i, rec in enumerate(recs or []):
            if not isinstance(rec, dict):
                continue
            sid = rec.get("session_id")
            if sid not in expected_set:
                if len(batch) == 1:
                    sid = expected_ids[0]
                elif i < len(expected_ids) and expected_ids[i] not in {r.get("session_id") for r in recs if isinstance(r, dict)}:
                    sid = expected_ids[i]
                else:
                    continue
            rec["session_id"] = sid
            out_file = runs_dir / f"conv-{sid}.json"
            out_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            wrote += 1
        stats["written"] += wrote
        if wrote < len(batch):
            log(f"Batch {batch_idx + 1} partial: {wrote}/{len(batch)} written")
        return wrote

    phase(f"Extract ({label}: {len(targets)} sessions in {len(batches)} batches)")
    log(f"Planned {len(batches)} batches for {len(targets)} missing sessions (concurrency={concurrency}, model={model_tier})")

    for w_start in range(0, len(batches), concurrency):
        wave = list(enumerate(batches[w_start : w_start + concurrency], start=w_start))
        log(f"Wave {w_start // concurrency + 1}: batches {w_start + 1}..{w_start + len(wave)} of {len(batches)}")
        await parallel(wave, lambda pair: run_one_batch(pair[0], pair[1]))

    log(f"Done: wrote {stats['written']}/{len(targets)} sessions, failed_batches={stats['failed']}")
    print({"targeted": len(targets), "batches": len(batches), "written": stats["written"], "failed_batches": stats["failed"]})
