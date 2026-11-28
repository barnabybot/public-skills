#!/usr/bin/env python3
"""skill-patterns pattern loop for one skill: sample traces, run the Wiki Maintainer,
run the Skill Proposer, verify the wiki. Method: arXiv 2608.27454 §3.1 to §3.2.

  python3 patterns.py sample   --manifest M.json --out DIR [--max 8 --max-fail 5 --max-pass 3 --cap 15000 --seed N]
  python3 patterns.py sample   --from-run RUN   --out DIR [...]   # manifest from this skill's data/; failure = verified friction
  python3 patterns.py maintain --wiki DIR --traces DIR --skill SKILL.md --iteration LABEL [--model opus] [--dry-run]
  python3 patterns.py propose  --wiki DIR --traces DIR --skill SKILL.md --out DIR --iteration LABEL [--model opus] [--dry-run]
  python3 patterns.py verify   --wiki DIR

Wiki layout: DIR/patterns/*.md, DIR/index.md, DIR/log.md, DIR/skill-impact.md. The Maintainer
writes the first three; `brun-skills gate` alone writes the ledger. The wiki is never reset.
A manifest is a JSON list of {"id", "outcome": "pass"|"fail", "files": [...], "note", "priority"}.
Prompts: prompts/wiki-maintainer.md (paper Appendix E.2), prompts/skill-proposer.md (E.3).
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import runner

PROMPTS = HERE / "prompts"
CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
INDEX_LINK = re.compile(r"^\s*-\s*\[([^\]]+)\]\((patterns/[^)]+\.md)\)")



def manifest_from_run(run):
    """One item per verified session; failure = any friction whose quote verified."""
    data = Path(run).expanduser() / "data"
    digests = {}
    for line in (data / "work-list.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            digests[r["session_id"]] = r["digest_path"]
    items = []
    for line in (data / "conversations.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        sid = c.get("session_id", "")
        if sid not in digests:
            continue
        failed = any(f.get("evidence_verified") for f in c.get("friction") or [])
        items.append({"id": sid, "outcome": "fail" if failed else "pass",
                      "files": [digests[sid]], "note": c.get("title", "")})
    return items


def choose(items, max_total=8, max_fail=5, max_pass=3, seed=0):
    """Stratified sample (Appendix C): at most max_fail failing and max_pass passing
    traces, lower `priority` first, seeded shuffle within a priority."""
    rng = random.Random(seed)

    def pick(outcome, n):
        pool = [i for i in items if i.get("outcome") == outcome]
        rng.shuffle(pool)
        pool.sort(key=lambda i: i.get("priority", 1))
        return pool[:n]

    return (pick("fail", max_fail) + pick("pass", max_pass))[:max_total]


def render_trace(item, cap=15000):
    head = [f"TRACE {item['id']}", f"outcome: {item['outcome']}"]
    if item.get("note"):
        head.append("note: " + " ".join(str(item["note"]).split()))
    parts = ["\n".join(head)]
    for f in item.get("files", []):
        p = Path(f).expanduser()
        body = p.read_text(errors="ignore") if p.is_file() else f"[missing file {p}]"
        parts.append(f"=== {p.name} ===\n{body}")
    text = "\n\n".join(parts)
    if len(text) > cap:
        text = text[:cap] + f"\n[truncated at {cap} characters]"
    return text


def cmd_sample(a):
    items = manifest_from_run(a.from_run) if a.from_run else json.loads(Path(a.manifest).expanduser().read_text())
    chosen = choose(items, a.max, a.max_fail, a.max_pass, a.seed)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    rows = ["| id | outcome | chars | note |", "|---|---|---:|---|"]
    for it in chosen:
        text = render_trace(it, a.cap)
        (out / f"{it['id']}.md").write_text(text)
        rows.append(f"| {it['id']} | {it['outcome']} | {len(text)} | {' '.join(str(it.get('note', '')).split())} |")
    fails = sum(1 for i in chosen if i["outcome"] == "fail")
    (out / "MANIFEST.md").write_text(
        f"# Sampled traces\n\n{len(chosen)} of {len(items)} candidates: {fails} failing, "
        f"{len(chosen) - fails} passing. Seed {a.seed}, cap {a.cap} characters.\n\n" + "\n".join(rows) + "\n")
    (out / "SAMPLE.json").write_text(json.dumps(
        {"seed": a.seed, "cap": a.cap, "chosen": [i["id"] for i in chosen]}, indent=2))
    print(f"sampled {len(chosen)}/{len(items)} traces ({fails} fail, {len(chosen) - fails} pass) -> {out}")
    return 0



def verify(wiki):
    """Deterministic checks on the wiki after a Maintainer pass. Returns problems."""
    wiki = Path(wiki)
    problems = []
    index = wiki / "index.md"
    if not index.is_file():
        return ["index.md missing"]
    linked = set()
    for line in index.read_text().splitlines():
        m = INDEX_LINK.match(line)
        if m:
            linked.add(m.group(2))
            if not (wiki / m.group(2)).is_file():
                problems.append(f"index links a missing page: {m.group(2)}")
    pages = sorted((wiki / "patterns").glob("*.md")) if (wiki / "patterns").is_dir() else []
    if not pages:
        problems.append("patterns/ has no pages")
    for p in pages:
        rel = f"patterns/{p.name}"
        if rel not in linked:
            problems.append(f"page not in index: {rel}")
        text = p.read_text()
        fm = text[4:].split("\n---\n", 1)[0] if text.startswith("---\n") else ""
        if not re.search(r"^evidence:", fm, re.M):
            problems.append(f"page lacks frontmatter with evidence: {rel}")
    log = wiki / "log.md"
    if not log.is_file() or not log.read_text().strip():
        problems.append("log.md missing or empty")
    return problems


def cmd_verify(a):
    problems = verify(Path(a.wiki).expanduser())
    for p in problems:
        print(f"problem: {p}")
    print(f"verify {a.wiki}: {'ok' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0



def skill_meta(skill):
    text = Path(skill).read_text()
    name = re.search(r"^name:\s*(.+)$", text, re.M)
    ver = re.search(r"^version:\s*(.+)$", text, re.M)
    return (name.group(1).strip() if name else Path(skill).stem), (ver.group(1).strip() if ver else "unversioned")


def trace_summary(traces):
    files = [p for p in sorted(Path(traces).glob("*.md")) if p.name != "MANIFEST.md"]
    fails = sum(1 for p in files if re.search(r"^outcome: fail", p.read_text(errors="ignore"), re.M))
    return len(files), fails


def run_context(iteration, skill, traces, extra=""):
    n, fails = trace_summary(traces)
    name, ver = skill_meta(skill)
    return (f"\n\n## This run\n\n- Iteration: {iteration}\n- Date: {datetime.now():%Y-%m-%d}\n"
            f"- Active skill: `{name}` version {ver}, at `SKILL.md`\n"
            f"- Traces: {n} under `traces/` ({fails} failing, {n - fails} passing); `traces/MANIFEST.md` lists them\n"
            + extra)


def note_line(a):
    return f"- Note: {a.note}\n" if getattr(a, "note", "") else ""


def run_agent(prompt_path, cwd, model, log, dry_run, harness="auto"):
    rc, _ = runner.run_prompt(
        prompt_path,
        cwd,
        harness=harness,
        model=model or "",
        log_path=log,
        dry_run=dry_run,
    )
    return rc


def cmd_maintain(a):
    wiki, traces, skill = (Path(x).expanduser().resolve() for x in (a.wiki, a.traces, a.skill))
    (wiki / "patterns").mkdir(parents=True, exist_ok=True)
    box = wiki / ".runs" / f"{datetime.now():%Y%m%d-%H%M%S}-maintain"
    box.mkdir(parents=True)
    os.symlink(wiki, box / "wiki")
    os.symlink(traces, box / "traces")
    shutil.copyfile(skill, box / "SKILL.md")
    before = len(list((wiki / "patterns").glob("*.md")))
    state = f"- Wiki state: {before} pattern pages; `wiki/index.md` {'present' if (wiki / 'index.md').is_file() else 'absent'}\n"
    prompt = box / "PROMPT.md"
    prompt.write_text((PROMPTS / "wiki-maintainer.md").read_text() + run_context(a.iteration, skill, traces, state + note_line(a)))
    rc = run_agent(prompt, box, a.model, box / "run.log", a.dry_run, harness=getattr(a, "harness", "auto"))
    if a.dry_run:
        return 0
    problems = verify(wiki)
    after = len(list((wiki / "patterns").glob("*.md")))
    print(f"maintain {a.iteration}: exit={rc} pages {before} -> {after}; sandbox {box}")
    for p in problems:
        print(f"  problem: {p}")
    return 1 if (rc or problems) else 0


def cmd_propose(a):
    wiki, traces, skill = (Path(x).expanduser().resolve() for x in (a.wiki, a.traces, a.skill))
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    snap = out / "wiki"
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir()
    for src in (wiki / "index.md", wiki / "log.md", *sorted(wiki.glob("skill-impact*.md"))):
        if src.is_file():
            shutil.copyfile(src, snap / src.name)
    shutil.copytree(wiki / "patterns", snap / "patterns")
    for p in snap.rglob("*.md"):
        p.chmod(0o444)
    if not (out / "traces").exists():
        os.symlink(traces, out / "traces")
    shutil.copyfile(skill, out / "SKILL.md")
    prompt = out / "PROMPT.md"
    prompt.write_text((PROMPTS / "skill-proposer.md").read_text() + run_context(a.iteration, skill, traces, note_line(a)))
    rc = run_agent(prompt, out, a.model, out / "run.log", a.dry_run, harness=getattr(a, "harness", "auto"))
    if a.dry_run:
        return 0
    patched, proposal = out / "SKILL-patched.md", out / "PROPOSAL.md"
    if not proposal.is_file():
        print(f"propose {a.iteration}: exit={rc}; PROPOSAL.md missing")
        return 1
    if not patched.is_file():
        print(f"propose {a.iteration}: exit={rc}; no_action (PROPOSAL.md only)")
        return 1 if rc else 0
    diff = subprocess.run(["diff", "-u", "SKILL.md", "SKILL-patched.md"], cwd=out,
                          capture_output=True, text=True).stdout
    (out / "patch.diff").write_text(diff)
    lines = diff.splitlines()
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    print(f"propose {a.iteration}: exit={rc}; patch.diff hunks={diff.count(chr(10) + '@@ ')} +{added} -{removed}; {out}")
    return 1 if rc else 0



def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--manifest")
    src.add_argument("--from-run")
    s.add_argument("--out", required=True)
    s.add_argument("--max", type=int, default=8)
    s.add_argument("--max-fail", type=int, default=5)
    s.add_argument("--max-pass", type=int, default=3)
    s.add_argument("--cap", type=int, default=15000)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_sample)

    for name, fn in (("maintain", cmd_maintain), ("propose", cmd_propose)):
        p = sub.add_parser(name)
        p.add_argument("--wiki", required=True)
        p.add_argument("--traces", required=True)
        p.add_argument("--skill", required=True)
        p.add_argument("--iteration", required=True)
        p.add_argument("--harness", default="auto", choices=runner.HARNESS_CHOICES)
        p.add_argument("--model", default="")
        p.add_argument("--note", default="", help="one line appended to the run context, for example a scope rule")
        p.add_argument("--dry-run", action="store_true")
        if name == "propose":
            p.add_argument("--out", required=True)
        p.set_defaults(fn=fn)

    v = sub.add_parser("verify")
    v.add_argument("--wiki", required=True)
    v.set_defaults(fn=cmd_verify)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
