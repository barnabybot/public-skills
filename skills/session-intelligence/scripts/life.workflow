"""Inline-prompt Antigravity run_workflow script for 7-lens behavioural portrait synthesis.

Pre-computes deterministic local-time rhythm statistics and packs verbatim user quotes inline
so all 7 lenses and the final portrait run with zero file or shell tool calls.

Args:
  scriptsDir (str): absolute path to session-intelligence/scripts
  root (str): absolute path to the run directory
  out (str, optional): destination JSON path (default: <root>/data/life-raw.json)
  lensModel (str, optional): model tier for lenses (default: "inherit")
  portraitModel (str, optional): model tier for final portrait (default: "inherit")
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

scripts_dir = str(args["scriptsDir"])
root = Path(str(args["root"])).expanduser()
out_path = Path(args.get("out") or root / "data" / "life-raw.json")
lens_model = str(args.get("lensModel") or "inherit")
portrait_model = str(args.get("portraitModel") or "inherit")

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import prompts_lib


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


data_dir = root / "data"
sd = data_dir / "synth"
wl = read_jsonl(data_dir / "work-list.jsonl")
convs = read_jsonl(data_dir / "conversations.jsonl")
profile = read_json(sd / "profile.json", {})
titles = read_json(sd / "titles.json", [])
clusters = read_json(sd / "candidate-clusters.json", [])
skill_friction = read_json(sd / "skill-friction.json", [])
preferences = read_json(sd / "preferences.json", [])
quotes = read_json(data_dir / "life" / "quotes.json", [])

import os
_tz_off = os.environ.get("SESSION_TZ_OFFSET", "").strip()
LOCAL_TZ = timezone(timedelta(hours=float(_tz_off))) if _tz_off else (datetime.now().astimezone().tzinfo or timezone.utc)
local_hours = Counter()
weekdays = Counter()
by_week_harness = Counter()
by_harness_turns = {}
marathons = []
for r in wl:
    h = r.get("harness", "unknown")
    d = r.get("date", "")
    if d:
        try:
            dt_day = datetime.strptime(d, "%Y-%m-%d")
            weekdays[dt_day.strftime("%a")] += 1
            iso_yr, iso_wk, _ = dt_day.isocalendar()
            by_week_harness[f"{iso_yr}-W{iso_wk:02d}:{h}"] += 1
        except ValueError:
            pass
    st = r.get("started_at") or ""
    en = r.get("ended_at") or ""
    dur_min = None
    if len(st) >= 19 and not st.endswith("T00:00:00Z"):
        try:
            dt_s = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
            local_hours[dt_s.hour] += 1
            if len(en) >= 19:
                dt_e = datetime.fromisoformat(en.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                dur_min = round((dt_e - dt_s).total_seconds() / 60.0, 1)
        except ValueError:
            pass
    bt = by_harness_turns.setdefault(h, {"n": 0, "transcripts": 0, "turns": 0, "corr": 0, "tools": 0})
    bt["n"] += 1
    if r.get("source_kind") == "transcript":
        bt["transcripts"] += 1
    bt["turns"] += int(r.get("human_turns") or 0)
    bt["corr"] += int(r.get("correction_hits") or 0)
    bt["tools"] += int(r.get("tool_calls") or 0)
    if r.get("source_kind") == "transcript":
        marathons.append({
            "date": d,
            "harness": h,
            "project": r.get("project"),
            "turns": r.get("human_turns"),
            "tools": r.get("tool_calls"),
            "corr": r.get("correction_hits"),
            "dur_min": dur_min,
            "score": r.get("score"),
            "first_msg": (r.get("first_message") or "")[:120],
        })

marathons.sort(key=lambda x: (x["score"] or 0), reverse=True)
rhythm_summary = {
    "total_sessions": len(wl),
    "raw_transcripts_with_timestamps": sum(local_hours.values()),
    "local_start_hour_histogram": {f"{h:02d}:00": local_hours.get(h, 0) for h in range(24) if local_hours.get(h, 0)},
    "weekday_counts": dict(weekdays),
    "by_harness": by_harness_turns,
    "top_25_sessions": marathons[:25],
    "weekly_harness_top": by_week_harness.most_common(40),
}

tr_ids = {c["session_id"] for c in convs if c.get("source_kind") == "transcript"}
tr_quotes = []
vault_quotes = []
for c in convs:
    is_tr = c["session_id"] in tr_ids
    base = f"[{c.get('date','')}|{c.get('harness','')}|{c.get('task_type','')}]"
    for q in (c.get("highlights") or []):
        if q:
            line = f"{base}[hi] {q[:160]}"
            (tr_quotes if is_tr else vault_quotes).append(line)
    for f in (c.get("friction") or []):
        q = f.get("quote") or ""
        if q:
            line = f"{base}[fr:{f.get('cost','')}] {q[:160]}"
            (tr_quotes if is_tr else vault_quotes).append(line)


def dedupe(seq, limit):
    seen, out = set(), []
    for s in seq:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
            if len(out) >= limit:
                break
    return out


tr_quotes_u = dedupe(tr_quotes, 1200)
vault_quotes_u = dedupe(vault_quotes, 800)

friction_quotes = [
    f"[{q.get('date','')}|{q.get('harness','')}|{q.get('cost','')}] {q.get('q','')}"
    for q in quotes
    if q.get("kind") == "friction"
]
pref_lines = [
    f"[{p.get('harness','')}] {p.get('rule','')} :: \"{p.get('quote','')}\""
    for p in preferences
]
titles_lines = "\n".join(
    f"{t.get('date','')} | {t.get('harness','')} | {t.get('task_type','')} | {t.get('title','')}"
    for t in titles
)
top_clusters = [
    {"kind": c.get("kind"), "target": c.get("target"), "count": c.get("count"), "examples": c.get("examples", [])[:3]}
    for c in clusters[:120]
]
sf_compact = [
    {"skill": s.get("skill"), "n": len(s.get("sessions") or []), "friction": (s.get("friction") or [])[:6]}
    for s in skill_friction[:50]
    if s.get("friction")
]

NO_TOOLS = "Do NOT call any file or shell tools; all data is provided inline below. Return your structured result immediately via finish."

lenses = [
    {
        "key": "rhythm",
        "focus": "When and how the user works: time-of-day (local time), session length, marathon sessions, harness switching across Codex/Muse/Grok/Antigravity/Claude Code/Cursor, context-switching across domains, and correction density.",
        "payload": (
            f"=== RHYTHM STATS (all {len(wl)} sessions) ===\n{json.dumps(rhythm_summary, ensure_ascii=False)}\n\n"
            f"=== SAMPLE TRANSCRIPT USER QUOTES ===\n" + "\n".join(tr_quotes_u[:200])
        ),
    },
    {
        "key": "steering",
        "focus": "How the user directs agents and sets standards: correction style, triggers for pushback, quality bar, and where they step in versus delegate.",
        "payload": (
            f"=== TOP SKILL FRICTION ===\n{json.dumps(sf_compact, ensure_ascii=False)}\n\n"
            f"=== FRICTION QUOTES ({len(friction_quotes)} total; showing first 500) ===\n" + "\n".join(friction_quotes[:500])
        ),
    },
    {
        "key": "values",
        "focus": "Non-negotiables and values: what they insist on repeatedly (voice, verification, simplicity, speed, aesthetics, autonomy).",
        "payload": f"=== ALL {len(pref_lines)} PREFERENCES ===\n" + "\n".join(pref_lines),
    },
    {
        "key": "rituals",
        "focus": "Operating system and repeated process moves: plan-first habits, handoffs, vault notes, retrospectives, parallel delegation, and skill packaging.",
        "payload": (
            f"=== PROFILE ===\n{json.dumps(profile, ensure_ascii=False)}\n\n"
            f"=== ALL {len(titles)} SESSION TITLES ===\n{titles_lines}"
        ),
    },
    {
        "key": "obsessions",
        "focus": "Projects, tools, and problems they keep returning to and refining across harnesses.",
        "payload": (
            f"=== TOP 120 CLUSTERS ===\n{json.dumps(top_clusters, ensure_ascii=False)}\n\n"
            f"=== ALL {len(titles)} SESSION TITLES ===\n{titles_lines}"
        ),
    },
    {
        "key": "emotion",
        "focus": "Energy: what excites or delights versus what drains or frustrates. Flow versus grind across sessions.",
        "payload": (
            f"=== RAW TRANSCRIPT VERBATIM QUOTES ({len(tr_quotes_u)}) ===\n" + "\n".join(tr_quotes_u) + "\n\n"
            f"=== VAULT NOTE QUOTES (sample {min(350, len(vault_quotes_u))}) ===\n" + "\n".join(vault_quotes_u[:350])
        ),
    },
    {
        "key": "tells",
        "focus": "Signature voice and idiosyncrasies: phrasing, dictation style and typos, brevity, and how they frame asks. Focus heavily on raw transcript user quotes where their real spoken/typed voice appears.",
        "payload": (
            f"=== RAW TRANSCRIPT VERBATIM USER QUOTES ({len(tr_quotes_u)}) ===\n" + "\n".join(tr_quotes_u)
        ),
    },
]


def lens_prompt(lens):
    return (
        f"{NO_TOOLS}\n\n"
        "Profile the user as a person from their real multi-harness agent sessions. Focus on repeating behavioural "
        "patterns across work and life.\n\n"
        f"Focus of this lens: {lens['focus']}\n\n"
        "Return 4-7 sharp patterns with `name` (short, memorable), `what` (concrete, specific), `evidence_quotes` "
        "(2-4 verbatim user quotes copied exactly from the data below, keeping exact typos), `frequency_hint`, and "
        "`reveals` (what it says about how they operate). Ground every pattern in real words.\n\n"
        f"{lens['payload']}"
    )


phase("Lenses (inline)")
log(f"Running {len(lenses)} behavioural lenses over {len(wl)} sessions (model={lens_model})")
findings = await parallel(
    lenses,
    lambda lens: agent(
        lens_prompt(lens),
        schema=prompts_lib.FIND_SCHEMA,
        role=f"Lens: {lens['key']}",
        model=lens_model,
    ),
)
merged = []
for lens, res in zip(lenses, findings):
    for pat in (res or {}).get("patterns") or []:
        merged.append({"lens": lens["key"], **pat})
log(f"Lenses complete: {len(merged)} raw patterns across {len(lenses)} lenses.")

phase("Portrait (inline)")
portrait_prompt = (
    f"{NO_TOOLS}\n\n"
    + prompts_lib.life_portrait_prompt(json.dumps(merged, ensure_ascii=False))
    + "\n\nUse British English and short declarative sentences. Avoid 'X, not Y' contrasts and em dashes."
)
profile_out = await agent(
    portrait_prompt,
    schema=prompts_lib.PROFILE_SCHEMA,
    role="Behavioural portrait",
    model=portrait_model,
)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(
    json.dumps({"result": {"profile": profile_out, "lens_findings": merged}}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
log(f"Life portrait saved to {out_path}.")
print({"out": str(out_path), "raw_patterns": len(merged), "portrait_patterns": len((profile_out or {}).get("patterns") or [])})
