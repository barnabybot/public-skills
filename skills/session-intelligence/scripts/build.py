#!/usr/bin/env python3
"""Assemble, verify, merge, and render the Session Intelligence roadmap and life portrait.

  python3 build.py assemble    --root <dir> [--dry-run]
  python3 build.py merge       --root <dir> --synth-out <file> [--dry-run]
  python3 build.py render      --root <dir> [--dry-run]
  python3 build.py merge-life  --root <dir> --synth-out <file> [--dry-run]
  python3 build.py render-life --root <dir> [--dry-run]

assemble runs deterministic evidence verification: every quote is matched
against the session's own digest so fabricated quotes cannot verify.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = DATA = APP = RUNS = None
TEMPLATES = Path(__file__).resolve().parent / "templates"
FONTS_DIR = Path(os.environ["SESSION_FONTS_DIR"]).expanduser() if os.environ.get("SESSION_FONTS_DIR") else None
FONT_SPECS = (
    ("ET Book", 400, "normal", "woff", "font/woff", "et-book/et-book-roman-old-style-figures/et-book-roman-old-style-figures.woff"),
    ("ET Book", 400, "italic", "woff", "font/woff", "et-book/et-book-display-italic-old-style-figures/et-book-display-italic-old-style-figures.woff"),
    ("Meta Pro", 400, "normal", "woff2", "font/woff2", "meta-pro/meta-pro-regular.woff2"),
    ("Meta Pro", 500, "normal", "woff2", "font/woff2", "meta-pro/meta-pro-medium.woff2"),
    ("Meta Pro", 700, "normal", "woff2", "font/woff2", "meta-pro/meta-pro-bold.woff2"),
    ("JetBrains Mono", 400, "normal", "truetype", "font/ttf", "jetbrains-mono/JetBrainsMono-Regular.ttf"),
)
META_KEYS = [
    "session_id",
    "harness",
    "host",
    "source_kind",
    "project",
    "vault_domain",
    "date",
    "human_turns",
    "assistant_turns",
    "tool_calls",
    "correction_hits",
    "score",
    "digest_path",
    "source_path",
    "resume_cmd",
    "vault_note",
    "vault_status",
    "first_message",
    "started_at",
    "ended_at",
]


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def quote_in(q: str, dnorm: str) -> bool:
    qn = norm(q)
    if not qn:
        return False
    return (qn[:30] if len(qn) > 30 else qn) in dnorm


def derive_observations(convs: list[dict]) -> list[dict]:
    obs = []
    for c in convs:
        base = dict(
            session_id=c.get("session_id", ""),
            harness=c.get("harness", ""),
            domain=c.get("vault_domain", ""),
            date=c.get("date", ""),
            title=c.get("title", ""),
        )
        for f in c.get("friction", []):
            obs.append({
                **base,
                "type": "friction",
                "subtype": f.get("type", ""),
                "text": f.get("what_went_wrong", ""),
                "evidence": f.get("quote", ""),
                "weight": f.get("cost", ""),
                "evidence_verified": f.get("evidence_verified", False),
            })
        for t in c.get("toil", []):
            obs.append({
                **base,
                "type": "toil",
                "subtype": t.get("frequency_hint", ""),
                "text": t.get("desc", ""),
                "evidence": t.get("evidence", ""),
                "weight": "",
                "evidence_verified": t.get("evidence_verified", False),
            })
        for p in c.get("preferences", []):
            obs.append({
                **base,
                "type": "preference",
                "subtype": "",
                "text": p.get("rule", ""),
                "evidence": p.get("quote", ""),
                "weight": "",
                "evidence_verified": p.get("evidence_verified", False),
            })
        for a in c.get("automation_candidates", []):
            obs.append({
                **base,
                "type": "automation",
                "subtype": a.get("kind", ""),
                "text": a.get("title", ""),
                "evidence": a.get("evidence", ""),
                "weight": a.get("payoff", ""),
                "target": a.get("target", ""),
                "evidence_verified": a.get("evidence_verified", False),
            })
    return obs


def build_synth_inputs(convs: list[dict]) -> None:
    sd = DATA / "synth"
    sd.mkdir(exist_ok=True)
    tt = Counter(c.get("task_type") for c in convs if c.get("task_type"))
    dom = Counter(c.get("vault_domain") for c in convs if c.get("vault_domain"))
    har = Counter(c.get("harness") or "unknown" for c in convs)
    vstat = Counter(c.get("vault_status") for c in convs if c.get("vault_status"))
    skillc: Counter[str] = Counter()
    for c in convs:
        for s in set(c.get("skills_invoked") or []):
            skillc[s] += 1
    cron_path = DATA / "cron-health.json"
    cron_health = json.loads(cron_path.read_text(encoding="utf-8")) if cron_path.is_file() else {}
    (sd / "profile.json").write_text(
        json.dumps(
            {
                "task_type_distribution": [{"task_type": k, "count": v} for k, v in tt.most_common()],
                "domain_distribution": [{"domain": k, "count": v} for k, v in dom.most_common()],
                "harness_distribution": [{"harness": k, "count": v} for k, v in har.most_common()],
                "vault_status_distribution": [{"status": k, "count": v} for k, v in vstat.most_common()],
                "top_skills": [{"skill": k, "count": v} for k, v in skillc.most_common(20)],
                "cron_health": cron_health,
                "n_sessions": len(convs),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sd / "titles.json").write_text(
        json.dumps(
            [
                {
                    "id": c["session_id"],
                    "date": c.get("date"),
                    "harness": c.get("harness", ""),
                    "domain": c.get("vault_domain"),
                    "vault_status": c.get("vault_status", ""),
                    "task_type": c.get("task_type"),
                    "title": c.get("title"),
                    "intent": (c.get("intent") or "")[:160],
                }
                for c in convs
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    clusters: dict[tuple[str, str], dict] = {}
    for c in convs:
        for a in c.get("automation_candidates") or []:
            kind = a.get("kind", "")
            if kind == "claude-md-rule":
                kind = "agents-md-rule"
            key = (kind, norm(a.get("target", "") or "new")[:40])
            cl = clusters.setdefault(
                key,
                {"kind": kind, "target": a.get("target", "") or "new", "count": 0, "sessions": [], "examples": []},
            )
            cl["count"] += 1
            cl["sessions"].append(c["session_id"])
            if len(cl["examples"]) < 6:
                cl["examples"].append({
                    "title": a.get("title", ""),
                    "evidence": (a.get("evidence", "") or "")[:200],
                    "domain": c.get("vault_domain"),
                    "harness": c.get("harness", ""),
                    "payoff": a.get("payoff", ""),
                    "effort": a.get("effort", ""),
                })
    (sd / "candidate-clusters.json").write_text(
        json.dumps(sorted(clusters.values(), key=lambda x: -x["count"]), ensure_ascii=False),
        encoding="utf-8",
    )
    sf: dict[str, dict] = {}
    for c in convs:
        sk = set(c.get("skills_invoked") or [])
        for fr in c.get("friction") or []:
            for s in sk:
                e = sf.setdefault(s, {"skill": s, "friction": [], "sessions": set()})
                e["sessions"].add(c["session_id"])
                if len(e["friction"]) < 12:
                    e["friction"].append({
                        "what": fr.get("what_went_wrong", ""),
                        "quote": (fr.get("quote", "") or "")[:160],
                        "session": c["session_id"],
                    })
        for s in c.get("skills_missing") or []:
            sf.setdefault("(missing) " + s, {"skill": "(missing) " + s, "friction": [], "sessions": set()})["sessions"].add(
                c["session_id"]
            )
    (sd / "skill-friction.json").write_text(
        json.dumps(
            sorted(
                ({"skill": v["skill"], "friction": v["friction"], "sessions": sorted(v["sessions"])} for v in sf.values()),
                key=lambda x: -len(x["friction"]),
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sd / "preferences.json").write_text(
        json.dumps(
            [
                {
                    "rule": p.get("rule", ""),
                    "quote": (p.get("quote", "") or "")[:160],
                    "session": c["session_id"],
                    "domain": c.get("vault_domain"),
                    "harness": c.get("harness", ""),
                }
                for c in convs
                for p in (c.get("preferences") or [])
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sd / "toil.json").write_text(
        json.dumps(
            [
                {
                    "desc": t.get("desc", ""),
                    "evidence": (t.get("evidence", "") or "")[:160],
                    "freq": t.get("frequency_hint", ""),
                    "session": c["session_id"],
                    "domain": c.get("vault_domain"),
                    "harness": c.get("harness", ""),
                }
                for c in convs
                for t in (c.get("toil") or [])
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def build_life_corpus(convs: list[dict]) -> None:
    """Build a deduped corpus of verbatim user quotes for the behavioural lenses."""
    ld = DATA / "life"
    ld.mkdir(exist_ok=True)
    seen: set[str] = set()
    quotes = []
    for c in convs:
        base = dict(date=c.get("date"), harness=c.get("harness", ""), domain=c.get("vault_domain"), task=c.get("task_type"))
        items = [("highlight", q, None) for q in (c.get("highlights") or [])]
        items += [("friction", f.get("quote"), f.get("cost")) for f in (c.get("friction") or [])]
        for kind, q, cost in items:
            if not q:
                continue
            k = re.sub(r"\s+", " ", q.lower()).strip()
            if len(k) < 6 or k in seen:
                continue
            seen.add(k)
            quotes.append({**base, "kind": kind, "cost": cost, "q": q[:140]})
    (ld / "quotes.json").write_text(json.dumps(quotes, ensure_ascii=False), encoding="utf-8")


def assemble(dry_run: bool = False) -> None:
    wl = {r["session_id"]: r for r in load_jsonl(DATA / "work-list.jsonl")}
    digcache: dict[str, str] = {}

    def dnorm_for(sid: str) -> str:
        if sid not in digcache:
            dp = wl.get(sid, {}).get("digest_path")
            digcache[sid] = norm(Path(dp).read_text(encoding="utf-8", errors="ignore") if dp and Path(dp).exists() else "")
        return digcache[sid]

    convs, parse_fail, orphans = [], [], []
    for f in sorted(RUNS.glob("conv-*.json")) if RUNS.exists() else []:
        raw = f.read_text(encoding="utf-8")
        try:
            rec = json.loads(raw)
        except Exception:
            try:
                rec = json.loads(raw[: raw.rfind("}") + 1])
            except Exception:
                parse_fail.append(f.name)
                continue
        sid = rec.get("session_id") or f.stem.replace("conv-", "")
        if sid not in wl:
            orphans.append(sid)
            if not dry_run:
                f.unlink()
            continue
        rec = {
            **{k: wl.get(sid, {}).get(k) for k in META_KEYS if wl.get(sid, {}).get(k) is not None},
            **rec,
            "session_id": sid,
        }
        dn = dnorm_for(sid)
        for fr in rec.get("friction", []):
            fr["evidence_verified"] = quote_in(fr.get("quote", ""), dn)
        for t in rec.get("toil", []):
            t["evidence_verified"] = quote_in(t.get("evidence", ""), dn)
        for p in rec.get("preferences", []):
            p["evidence_verified"] = quote_in(p.get("quote", ""), dn)
        for a in rec.get("automation_candidates", []):
            a["evidence_verified"] = quote_in(a.get("evidence", ""), dn)
        convs.append(rec)

    convs.sort(key=lambda c: (c.get("date") or ""), reverse=True)
    obs = derive_observations(convs)
    want, have = set(wl.keys()), {c["session_id"] for c in convs}
    if not dry_run:
        (DATA / "conversations.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in convs) + ("\n" if convs else ""),
            encoding="utf-8",
        )
        (DATA / "observations.jsonl").write_text(
            "\n".join(json.dumps(o, ensure_ascii=False) for o in obs) + ("\n" if obs else ""),
            encoding="utf-8",
        )
        (DATA / "synth-input.json").write_text(
            json.dumps(
                [
                    {
                        "id": c["session_id"],
                        "harness": c.get("harness", ""),
                        "domain": c.get("vault_domain"),
                        "date": c.get("date"),
                        "task_type": c.get("task_type"),
                        "title": c.get("title"),
                        "skills_invoked": c.get("skills_invoked", []),
                        "skills_missing": c.get("skills_missing", []),
                        "friction": c.get("friction", []),
                        "toil": c.get("toil", []),
                        "preferences": c.get("preferences", []),
                        "automation_candidates": c.get("automation_candidates", []),
                        "outcome": c.get("outcome", {}),
                    }
                    for c in convs
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        build_synth_inputs(convs)
        build_life_corpus(convs)
        (DATA / "missing-full.json").write_text(
            json.dumps([{"session_id": s} for s in sorted(want - have)], ensure_ascii=False),
            encoding="utf-8",
        )
    ver = sum(1 for o in obs if o.get("evidence_verified"))
    tot = sum(1 for o in obs if (o.get("evidence") or "").strip())
    prefix = "[dry-run] " if dry_run else ""
    print(
        f"{prefix}conversations: {len(convs)} | observations: {len(obs)} | "
        f"evidence verified: {ver}/{tot} ({round(100 * ver / tot) if tot else 0}%)"
    )
    print(
        f"{prefix}orphans removed: {len(orphans)} | parse failures: {len(parse_fail)} | "
        f"missing vs work-list ({len(want)}): {len(want - have)}"
    )


def _unwrap_result(raw: dict) -> dict:
    inner = raw.get("result")
    return inner if isinstance(inner, dict) else raw


def merge(synth_out: str, dry_run: bool = False) -> None:
    r = _unwrap_result(json.loads(Path(synth_out).expanduser().read_text(encoding="utf-8")))
    prof_path = DATA / "synth" / "profile.json"
    prof = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else {}
    rm, bk, nw, rl, ps = (r.get(k) or {} for k in ("roadmap", "backlog", "newwork", "rules", "profile_summary"))
    rules_list = rl.get("agents_md_rules") if "agents_md_rules" in rl else rl.get("claude_md_rules", [])
    payload = {
        "generated_for": "full",
        "headline": rm.get("headline", ""),
        "profile": {
            "task_type_distribution": prof.get("task_type_distribution", []),
            "domain_distribution": prof.get("domain_distribution", []),
            "harness_distribution": prof.get("harness_distribution", []),
            "vault_status_distribution": prof.get("vault_status_distribution", []),
            "cron_health": prof.get("cron_health", {}),
            "top_skills": prof.get("top_skills", []),
            "summary": ps.get("summary", ""),
            "recurring_patterns": ps.get("recurring_patterns", []),
        },
        "automation_themes": rm.get("automation_themes", []),
        "skill_backlog": bk.get("skill_backlog", []),
        "new_skills": nw.get("new_skills", []),
        "new_crons": nw.get("new_crons", []),
        "agents_md_rules": rules_list or [],
    }
    if not dry_run:
        (DATA / "synthesis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'[dry-run] ' if dry_run else ''}merged synthesis.json")


def merge_life(synth_out: str, dry_run: bool = False) -> None:
    r = _unwrap_result(json.loads(Path(synth_out).expanduser().read_text(encoding="utf-8")))
    prof_path = DATA / "synth" / "profile.json"
    prof = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else {}
    payload = {
        "profile": r.get("profile", {}),
        "lens_findings": r.get("lens_findings", []),
        "harnesses": [h.get("harness") for h in prof.get("harness_distribution", []) if h.get("harness")],
    }
    if not dry_run:
        (DATA / "life.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'[dry-run] ' if dry_run else ''}merged life.json")


def build_font_css(fonts_dir: Path | None = None) -> str:
    base = FONTS_DIR if fonts_dir is None else fonts_dir
    if base is None or not base.is_dir():
        return ""
    rules = []
    for family, weight, style, fmt, mime, rel in FONT_SPECS:
        path = base / rel
        if not path.is_file():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:{style};'
            f'font-display:swap;src:url("data:{mime};base64,{b64}") format("{fmt}");}}'
        )
    return "\n".join(rules)


def _local_tz():
    offset = os.environ.get("SESSION_TZ_OFFSET", "").strip()
    if offset:
        return timezone(timedelta(hours=float(offset))), os.environ.get("SESSION_TZ_LABEL", f"UTC{offset}")
    now_local = datetime.now().astimezone()
    return now_local.tzinfo or timezone.utc, now_local.tzname() or "local"


def compute_rhythm(convs: list[dict]) -> dict:
    tz, tz_label = _local_tz()
    hours: Counter[str] = Counter()
    dates = sorted(c.get("date") for c in convs if c.get("date"))
    for c in convs:
        st = c.get("started_at") or ""
        if len(st) >= 19 and not st.endswith("T00:00:00Z"):
            try:
                dt = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(tz)
                hours[f"{dt.hour:02d}"] += 1
            except ValueError:
                pass
    return {
        "n_sessions": len(convs),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "tz_label": tz_label,
        "local_hours": dict(sorted(hours.items())),
    }


def compute_life_sessions(convs: list[dict]) -> list[dict]:
    tz, _ = _local_tz()
    rows: list[dict] = []
    for c in convs:
        d = c.get("date") or ""
        h = None
        st = c.get("started_at") or ""
        if len(st) >= 19 and not st.endswith("T00:00:00Z"):
            try:
                dt = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(tz)
                h = dt.hour
            except ValueError:
                pass
        wd = None
        if len(d) >= 10:
            try:
                wd = datetime.strptime(d[:10], "%Y-%m-%d").weekday()
            except ValueError:
                pass
        rows.append({"d": d, "hr": c.get("harness") or "", "h": h, "wd": wd})
    return rows


def _resolve_cron_dir(hh: dict, agents_vault: Path | None) -> Path | None:
    if agents_vault is not None:
        cand = agents_vault / "Cron" / "sessions"
        if cand.is_dir():
            return cand
    for fail in hh.get("recent_failures") or []:
        np = fail.get("note_path") or ""
        if np:
            parent = Path(np).expanduser().parent
            if parent.is_dir():
                return parent
    if ROOT is not None:
        for anc in ROOT.resolve().parents:
            cand = anc / "Cron" / "sessions"
            if cand.is_dir():
                return cand
    return None


def _ensure_cron_daily(hh: dict, agents_vault: Path | None, date_range: list[str] | None) -> dict:
    if not isinstance(hh, dict) or hh.get("daily"):
        return hh
    if not hh.get("total_runs") and agents_vault is None:
        return hh
    cron_dir = _resolve_cron_dir(hh, agents_vault)
    if cron_dir is None:
        return hh
    import sys

    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import sources

    since_date = date_range[0] if date_range else ""
    daily = sources.scan_cron_daily(cron_dir, since_date=since_date)
    if not daily:
        return hh
    updated = dict(hh)
    updated["daily"] = daily
    return updated


def _attach_theme_sessions(synth: dict, data_dir: Path) -> None:
    themes = synth.get("automation_themes")
    clusters_path = data_dir / "synth" / "candidate-clusters.json"
    if not isinstance(themes, list) or not themes or not clusters_path.is_file():
        return
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    orig_sids = [set(t.get("evidence_sessions") or []) for t in themes]
    theme_sids = [set(s) for s in orig_sids]
    theme_texts = [f"{t.get('title', '')} {t.get('proposed_action', '')}".lower() for t in themes]
    for cl in clusters:
        cl_s = set(cl.get("sessions") or [])
        tgt = (cl.get("target") or "").lower().strip()
        best_i, best_sc = -1, 0
        for i, t in enumerate(themes):
            if cl.get("kind") != t.get("kind"):
                continue
            overlap = len(cl_s & orig_sids[i])
            tgt_hit = bool(tgt and tgt != "new" and len(tgt) >= 3 and re.search(r"\b" + re.escape(tgt) + r"\b", theme_texts[i]))
            if overlap == 0 and not tgt_hit:
                continue
            sc = overlap * 3 + (5 if tgt_hit else 0)
            if sc > best_sc:
                best_sc, best_i = sc, i
        if best_i >= 0:
            theme_sids[best_i] |= cl_s
    for i, t in enumerate(themes):
        if theme_sids[i]:
            t["matched_sessions"] = sorted(theme_sids[i])


def render(dry_run: bool = False, agents_vault: Path | None = None) -> None:
    convs, obs = load_jsonl(DATA / "conversations.jsonl"), load_jsonl(DATA / "observations.jsonl")
    synth = json.loads((DATA / "synthesis.json").read_text(encoding="utf-8")) if (DATA / "synthesis.json").exists() else {}
    dates = sorted([c.get("date") for c in convs if c.get("date")])
    synth.setdefault("n_sessions", len(convs))
    if dates:
        synth.setdefault("date_range", [dates[0], dates[-1]])
    _attach_theme_sessions(synth, DATA)
    prof = synth.get("profile")
    if isinstance(prof, dict):
        hh = prof.get("cron_health")
        if not hh and (DATA / "cron-health.json").is_file():
            hh = json.loads((DATA / "cron-health.json").read_text(encoding="utf-8"))
        if isinstance(hh, dict):
            prof["cron_health"] = _ensure_cron_daily(hh, agents_vault, synth.get("date_range"))
    blob = json.dumps({"conversations": convs, "synthesis": synth, "observations": obs}, ensure_ascii=False).replace("</", "<\\/")
    if not dry_run:
        fonts_css = build_font_css()
        APP.mkdir(parents=True, exist_ok=True)
        html = (
            (TEMPLATES / "app.html")
            .read_text(encoding="utf-8")
            .replace("__FONTS__", fonts_css)
            .replace("__DATA__", blob)
        )
        (APP / "index.html").write_text(html, encoding="utf-8")
    print(
        f"{'[dry-run] ' if dry_run else ''}rendered {APP / 'index.html'} "
        f"({len(convs)} conv, {len(obs)} obs, {len(synth.get('automation_themes', []))} themes)"
    )


def render_life(dry_run: bool = False) -> None:
    life = json.loads((DATA / "life.json").read_text(encoding="utf-8")) if (DATA / "life.json").exists() else {}
    payload = dict(life)
    convs_path = DATA / "conversations.jsonl"
    if convs_path.exists():
        convs = load_jsonl(convs_path)
        if convs or "rhythm" not in payload:
            payload["rhythm"] = compute_rhythm(convs)
        if convs:
            payload["sessions"] = compute_life_sessions(convs)
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    if not dry_run:
        fonts_css = build_font_css()
        APP.mkdir(parents=True, exist_ok=True)
        html = (
            (TEMPLATES / "life.html")
            .read_text(encoding="utf-8")
            .replace("__FONTS__", fonts_css)
            .replace("__DATA__", blob)
        )
        (APP / "life.html").write_text(html, encoding="utf-8")
    print(f"{'[dry-run] ' if dry_run else ''}rendered {APP / 'life.html'} ({len(life.get('profile', {}).get('patterns', []))} patterns)")


def main(argv: list[str] | None = None) -> int:
    global ROOT, DATA, APP, RUNS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["assemble", "merge", "render", "merge-life", "render-life", "all"], help="pipeline stage to run")
    ap.add_argument("--root", required=True, help="run directory containing data/ and app/")
    ap.add_argument("--synth-out", default="", help="workflow or runner output JSON file for merge / merge-life")
    ap.add_argument("--out-dir", default="", help="override output app directory for render / render-life")
    ap.add_argument("--agents-vault", default="", help="override agent notes directory for scheduled-job daily backfill")
    ap.add_argument("--dry-run", action="store_true", help="compute and report without writing files")
    a = ap.parse_args(argv)
    ROOT = Path(a.root).expanduser()
    DATA, RUNS = ROOT / "data", ROOT / "data" / "runs"
    APP = Path(a.out_dir).expanduser() if a.out_dir else ROOT / "app"
    vault_dir = Path(a.agents_vault).expanduser() if a.agents_vault else None
    if a.mode in ("assemble", "all"):
        assemble(dry_run=a.dry_run)
    if a.mode == "merge":
        merge(a.synth_out, dry_run=a.dry_run)
    if a.mode == "merge-life":
        merge_life(a.synth_out, dry_run=a.dry_run)
    if a.mode in ("render", "all"):
        render(dry_run=a.dry_run, agents_vault=vault_dir)
    if a.mode == "render-life":
        render_life(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
