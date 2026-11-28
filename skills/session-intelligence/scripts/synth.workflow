"""Inline-prompt Antigravity run_workflow script for Session Intelligence roadmap synthesis.

Reads <root>/data/synth/* in Python and embeds compact full-corpus payloads directly
into each agent prompt so workflow agents require zero file or shell tool calls.

Args:
  scriptsDir (str): absolute path to session-intelligence/scripts
  root (str): absolute path to the run directory
  out (str, optional): destination JSON path (default: <root>/data/synth-raw.json)
  model (str, optional): Antigravity model tier (default: "inherit")
"""
import json
import sys
from pathlib import Path

scripts_dir = str(args["scriptsDir"])
root = Path(str(args["root"])).expanduser()
out_path = Path(args.get("out") or root / "data" / "synth-raw.json")
model_tier = str(args.get("model") or "inherit")

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import prompts_lib


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


sd = root / "data" / "synth"
profile = read_json(sd / "profile.json", {})
titles = read_json(sd / "titles.json", [])
clusters = read_json(sd / "candidate-clusters.json", [])
skill_friction = read_json(sd / "skill-friction.json", [])
preferences = read_json(sd / "preferences.json", [])
toil = read_json(sd / "toil.json", [])

profile_txt = json.dumps(profile, ensure_ascii=False)
titles_lines = "\n".join(
    f"{t.get('id','')} | {t.get('date','')} | {t.get('harness','')} | {t.get('task_type','')} | {t.get('vault_status','')} | {t.get('title','')}"
    for t in titles
)
top_clusters = [c for c in clusters if c.get("count", 0) >= 2]
if len(top_clusters) < 220:
    singles = [c for c in clusters if c.get("count", 0) < 2]
    top_clusters.extend(singles[: max(0, 220 - len(top_clusters))])
clusters_txt = json.dumps(top_clusters, ensure_ascii=False)

sf_compact = [
    {
        "skill": s.get("skill"),
        "n_sessions": len(s.get("sessions") or []),
        "sessions": (s.get("sessions") or [])[:15],
        "friction": s.get("friction") or [],
    }
    for s in skill_friction
    if (s.get("friction") or str(s.get("skill", "")).startswith("(missing)"))
]
sf_txt = json.dumps(sf_compact[:120], ensure_ascii=False)

new_clusters = [c for c in clusters if c.get("kind") in ("new-skill", "new-cron")]
toil_lines = "\n".join(
    f"[{t.get('session','')[:12]}|{t.get('harness','')}|{t.get('freq','')}] {t.get('desc','')} :: \"{t.get('evidence','')}\""
    for t in toil
)
pref_lines = "\n".join(
    f"[{p.get('session','')[:12]}|{p.get('harness','')}] {p.get('rule','')} :: \"{p.get('quote','')}\""
    for p in preferences
)

kinds_str = "|".join(prompts_lib.KINDS)
NO_TOOLS = "Do NOT call any file or shell tools; all data is provided inline below. Return your structured result immediately via finish."

tasks = [
    {
        "key": "profile_summary",
        "label": "synth:profile",
        "schema": prompts_lib.PSUM_SCHEMA,
        "prompt": (
            f"{NO_TOOLS}\n\n"
            "Write a crisp 2-3 sentence summary (British English, short declarative sentences) of how the user spends time "
            "across their multi-harness agent fleet and where effort concentrates, plus `recurring_patterns`: repeated kinds "
            "of work across multiple sessions, each with a count and supporting session ids.\n\n"
            f"=== PROFILE.JSON ===\n{profile_txt}\n\n"
            f"=== ALL {len(titles)} SESSIONS (id | date | harness | task_type | status | title) ===\n{titles_lines}"
        ),
    },
    {
        "key": "roadmap",
        "label": "synth:roadmap",
        "schema": prompts_lib.ROADMAP_SCHEMA,
        "prompt": (
            f"{NO_TOOLS}\n\n"
            f"Build one ranked automation ROADMAP across all {profile.get('n_sessions')} sessions. "
            f"Merge near-duplicate clusters into 12-18 coherent, high-leverage themes. Each theme needs title, kind ({kinds_str}), "
            "rationale, frequency (supporting sessions), est_effort, est_payoff (low|medium|high), "
            "automation_score = round(frequency * payoffWeight / effortWeight, 1) with low=1 medium=2 high=3, "
            "proposed_action, evidence_sessions, and example_quotes (1-2 verbatim from the clusters below). "
            "Check cron_health in profile so you do not duplicate working scheduled jobs (instead propose fixes for failing ones). "
            "Sort by automation_score desc. Set headline to the single highest-leverage opportunity.\n\n"
            f"=== PROFILE.JSON (incl. cron_health) ===\n{profile_txt}\n\n"
            f"=== TOP {len(top_clusters)} CANDIDATE CLUSTERS (of {len(clusters)}) ===\n{clusters_txt}"
        ),
    },
    {
        "key": "backlog",
        "label": "synth:skill-backlog",
        "schema": prompts_lib.BACKLOG_SCHEMA,
        "prompt": (
            f"{NO_TOOLS}\n\n"
            "Produce `skill_backlog`: for each skill with real, repeated friction provide `skill`, `friction_count`, "
            "`issues`, `proposed_edits` (concrete SKILL.md changes), and `sessions`. Include only evidenced skills (top 15-25), "
            "sorted by friction_count desc.\n\n"
            f"=== SKILL FRICTION ({len(sf_compact)} skills) ===\n{sf_txt}"
        ),
    },
    {
        "key": "newwork",
        "label": "synth:new-work",
        "schema": prompts_lib.NEWWORK_SCHEMA,
        "prompt": (
            f"{NO_TOOLS}\n\n"
            "Produce `new_skills` (name, problem, recurring_in, sketch) and `new_crons` (name, cadence, what, sessions). "
            "Check `cron_health` in profile.json so you do NOT propose duplicate scheduled jobs that already run. "
            "Include only repetition-evidenced items grounded in the toil and candidate clusters below.\n\n"
            f"=== PROFILE.JSON (incl. cron_health) ===\n{profile_txt}\n\n"
            f"=== NEW-SKILL / NEW-CRON CLUSTERS ({len(new_clusters)}) ===\n{json.dumps(new_clusters[:120], ensure_ascii=False)}\n\n"
            f"=== ALL {len(toil)} TOIL OBSERVATIONS ===\n{toil_lines}"
        ),
    },
    {
        "key": "rules",
        "label": "synth:agents-md",
        "schema": prompts_lib.RULES_SCHEMA,
        "prompt": (
            f"{NO_TOOLS}\n\n"
            "Extract `agents_md_rules`: durable preferences or repeated corrections that should become hard rules in AGENTS.md "
            "across all harnesses. Merge near-duplicates into the strongest 12-20 rules. Each item needs `rule` (imperative, "
            "short declarative British English), `evidence_quotes` (1-3 verbatim quotes copied from below), and `sessions`. "
            "Include only quote-backed rules.\n\n"
            f"=== ALL {len(preferences)} PREFERENCE OBSERVATIONS ===\n{pref_lines}"
        ),
    },
]

phase("Synthesise (inline)")
log(f"Running {len(tasks)} parallel synthesis agents over {profile.get('n_sessions')} sessions (model={model_tier})")
outputs = await parallel(
    tasks,
    lambda t: agent(
        t["prompt"],
        schema=t["schema"],
        role=t["label"],
        model=model_tier,
    ),
)
merged = {t["key"]: out for t, out in zip(tasks, outputs)}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({"result": merged}, ensure_ascii=False, indent=2), encoding="utf-8")
themes = len((merged.get("roadmap") or {}).get("automation_themes") or [])
backlog = len((merged.get("backlog") or {}).get("skill_backlog") or [])
rules = len((merged.get("rules") or {}).get("agents_md_rules") or [])
log(f"Synthesis saved to {out_path}: {themes} themes, {backlog} skill items, {rules} AGENTS.md rules.")
print({"out": str(out_path), "themes": themes, "skill_backlog": backlog, "agents_md_rules": rules})
